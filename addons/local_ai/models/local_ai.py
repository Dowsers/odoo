# -*- coding: utf-8 -*-
"""Connector to the Ollama server of the company network."""
import ipaddress
import json
import logging
import re
import socket
import time
from datetime import datetime
from urllib.parse import urlsplit

import requests
from markupsafe import Markup

from odoo import _, api, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

PARAM_URL = 'local_ai.url'
PARAM_MODEL = 'local_ai.model'
PARAM_TIMEOUT = 'local_ai.timeout'
# "False" lets the connector reach an address outside Tailscale (not recommended).
PARAM_TAILSCALE_ONLY = 'local_ai.tailscale_only'
DEFAULT_MODEL = 'qwen3.5:2b'
DEFAULT_TIMEOUT = 120
TAILSCALE_NETWORKS = (
    ipaddress.ip_network('100.64.0.0/10'),
    ipaddress.ip_network('fd7a:115c:a1e0::/48'),
)
THINK_BLOCK = re.compile(r'<think>.*?</think>', re.DOTALL | re.IGNORECASE)
CODE_FENCE = re.compile(r'^```[a-zA-Z]*\s*|\s*```$')
BULLET = re.compile(r'^(?:[-*•]|\d+[.)])\s+(.*)$')
MARKDOWN = re.compile(r'\*\*|__|^#+\s*')


def resolve_host(host, port):
    """Addresses of ``host`` (separate function so that tests can replace it)."""
    return sorted({info[4][0].split('%')[0] for info in socket.getaddrinfo(host, port, proto=socket.IPPROTO_TCP)})


class LocalAIError(UserError):
    """The local AI server could not answer."""


class LocalAI(models.AbstractModel):
    _name = 'local.ai'
    _description = 'Local AI (Ollama)'

    # ------------------------------------------------------------------
    # Configuration
    # ------------------------------------------------------------------
    @api.model
    def _get_config(self):
        ICP = self.env['ir.config_parameter'].sudo()
        try:
            timeout = max(5, int(ICP.get_param(PARAM_TIMEOUT) or DEFAULT_TIMEOUT))
        except ValueError:
            timeout = DEFAULT_TIMEOUT
        return {
            'url': (ICP.get_param(PARAM_URL) or '').strip().rstrip('/'),
            'model': (ICP.get_param(PARAM_MODEL) or DEFAULT_MODEL).strip(),
            'timeout': timeout,
            'tailscale_only': str(ICP.get_param(PARAM_TAILSCALE_ONLY, 'True')).strip().lower()
            not in ('false', '0', 'no', 'non'),
        }

    @api.model
    def _is_enabled(self):
        return bool(self._get_config()['url'])

    @api.model
    def _check_url(self, url, tailscale_only=True):
        """Refuse an invalid address and, unless allowed, an address that does
        not resolve into the Tailscale network."""
        parts = urlsplit(url)
        if parts.scheme not in ('http', 'https') or not parts.hostname:
            raise LocalAIError(_("Invalid address of the AI server: %s", url))
        if not tailscale_only:
            return
        port = parts.port or (443 if parts.scheme == 'https' else 80)
        try:
            addresses = resolve_host(parts.hostname, port)
        except OSError as error:
            raise LocalAIError(_(
                "The AI server %(host)s cannot be found: %(error)s", host=parts.hostname, error=error)) from error
        outside = [address for address in addresses
                   if not any(ipaddress.ip_address(address) in network for network in TAILSCALE_NETWORKS)]
        if not addresses or outside:
            raise LocalAIError(_(
                "The AI server %(host)s resolves to %(addresses)s, outside the Tailscale network: "
                "the request was not sent.", host=parts.hostname, addresses=', '.join(outside or addresses)))

    # ------------------------------------------------------------------
    # Requests
    # ------------------------------------------------------------------
    @api.model
    def _request(self, method, path, payload=None, timeout=None):
        config = self._get_config()
        if not config['url']:
            raise LocalAIError(_(
                "The local AI is not configured: set the address of the Ollama server in Settings, "
                "General Settings, Local AI."))
        self._check_url(config['url'], config['tailscale_only'])
        try:
            response = requests.request(
                method, config['url'] + path, json=payload, timeout=(10, timeout or config['timeout']))
        except requests.Timeout as error:
            raise LocalAIError(_(
                "The AI server did not answer within %s seconds. It may be busy: try again later.",
                timeout or config['timeout'])) from error
        except requests.RequestException as error:
            raise LocalAIError(_("The AI server cannot be reached: %s", error)) from error
        try:
            data = response.json()
        except ValueError:
            data = {}
        if response.status_code != 200:
            detail = data.get('error') if isinstance(data, dict) else None
            raise LocalAIError(_(
                "The AI server returned an error (%(status)s): %(detail)s",
                status=response.status_code, detail=detail or response.text[:200]))
        return data

    @api.model
    def _chat(self, messages, *, system=None, temperature=0.2, json_format=False, images=None,
              num_ctx=None, max_tokens=None, model=None, timeout=None):
        """Answer of the model to ``messages`` (list of {'role', 'content'}).

        :param images: base64 images attached to the last message (vision models)
        :return: the text of the answer, without thinking block
        """
        config = self._get_config()
        chat = [{'role': 'system', 'content': system}] if system else []
        chat += [{'role': message['role'], 'content': message['content']} for message in messages]
        if images:
            chat[-1] = dict(chat[-1], images=list(images))
        payload = {
            'model': model or config['model'],
            'messages': chat,
            'stream': False,
            'think': False,
            'keep_alive': '10m',
            'options': {'temperature': temperature},
        }
        if num_ctx:
            payload['options']['num_ctx'] = num_ctx
        if max_tokens:
            payload['options']['num_predict'] = max_tokens
        if json_format:
            payload['format'] = 'json'
        start = time.monotonic()
        data = self._request('POST', '/api/chat', payload, timeout=timeout)
        try:
            content = data['message']['content']
        except (KeyError, TypeError) as error:
            raise LocalAIError(_("Unexpected answer from the AI server.")) from error
        # the content is never logged: it may hold confidential data
        _logger.info("Local AI: %s, %s+%s tokens, %.1f s", payload['model'], data.get('prompt_eval_count'),
                     data.get('eval_count'), time.monotonic() - start)
        return THINK_BLOCK.sub('', content or '').strip()

    @api.model
    def _chat_json(self, messages, **kwargs):
        """Like _chat, for an answer that must be a JSON object."""
        answer = self._chat(messages, json_format=True, **kwargs)
        try:
            data = json.loads(CODE_FENCE.sub('', answer.strip()))
        except ValueError as error:
            raise LocalAIError(_("The AI server did not answer with valid data.")) from error
        if not isinstance(data, dict):
            raise LocalAIError(_("The AI server did not answer with valid data."))
        return data

    @api.model
    def _text_to_html(self, text):
        """HTML of a plain text answer: paragraphs and lists (lines starting
        with "- ", "* " or "1. "); markdown emphasis and titles are dropped."""
        blocks, items = [], []

        def flush():
            if items:
                blocks.append(Markup('<ul>%s</ul>') % Markup('').join(Markup('<li>%s</li>') % item for item in items))
                items.clear()

        for raw in (text or '').splitlines():
            line = MARKDOWN.sub('', raw).strip()
            if not line:
                flush()
                continue
            bullet = BULLET.match(line)
            if bullet:
                items.append(bullet.group(1).strip())
                continue
            flush()
            blocks.append(Markup('<p>%s</p>') % line)
        flush()
        return Markup('').join(blocks)

    @api.model
    def _first_line(self, text, max_length=200):
        """First non-empty line of an answer, without bullet nor quotes."""
        for raw in (text or '').splitlines():
            line = MARKDOWN.sub('', raw).strip()
            bullet = BULLET.match(line)
            line = (bullet.group(1) if bullet else line).strip().strip('"«»“”\'').strip()
            if line:
                return line[:max_length]
        return ''

    @api.model
    def _test_connection(self):
        """Version of the server, models installed and a short answer of the
        configured model, as a message for the settings."""
        config = self._get_config()
        version = self._request('GET', '/api/version', timeout=15).get('version', '?')
        models_installed = [model.get('name') for model in self._request('GET', '/api/tags', timeout=15).get('models', [])]
        if config['model'] not in models_installed:
            raise LocalAIError(_(
                "The model %(model)s is not installed on the AI server. Installed models: %(models)s.",
                model=config['model'], models=', '.join(models_installed) or '-'))
        start = time.monotonic()
        answer = self._chat([{'role': 'user', 'content': 'Réponds uniquement : OK'}], max_tokens=10)
        return _(
            "Ollama %(version)s answers through %(url)s. Model %(model)s: \"%(answer)s\" in %(seconds).1f s.",
            version=version, url=config['url'], model=config['model'], answer=answer[:40],
            seconds=time.monotonic() - start)

    # ------------------------------------------------------------------
    # Queue
    # ------------------------------------------------------------------
    @api.model
    def _queue_models(self):
        names = self.env.registry.descendants(['local.ai.queue.mixin'], '_inherit')
        return [name for name in names if name != 'local.ai.queue.mixin' and not self.env[name]._abstract]

    @api.model
    def _cron_process_queue(self):
        """Scheduled action: process the queued records, oldest first, one
        transaction per record."""
        Cron = self.env['ir.cron']
        queue_models = self._queue_models()
        while True:
            counts = {name: self.env[name].sudo().search_count([('ai_state', '=', 'queued')]) for name in queue_models}
            total = sum(counts.values())
            if not total:
                Cron._commit_progress(remaining=0)
                return
            oldest = [self.env[name].sudo().search([('ai_state', '=', 'queued')], order='ai_date, id', limit=1)
                      for name, count in counts.items() if count]
            record = min(oldest, key=lambda record: (record.ai_date or datetime.min, record.id))
            # notes and errors in the language of the person who created the record
            lang = record.create_uid.lang or self.env.lang
            record.with_context(lang=lang)._local_ai_run()
            if Cron._commit_progress(1, remaining=total - 1) < 60:
                return
