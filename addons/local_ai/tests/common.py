# -*- coding: utf-8 -*-
"""Helpers to test the local AI without an Ollama server."""
import json
from contextlib import contextmanager
from unittest.mock import patch

RESOLVE = 'odoo.addons.local_ai.models.local_ai.resolve_host'
REQUEST = 'odoo.addons.local_ai.models.local_ai.requests.request'
TAILSCALE_ADDRESS = '100.64.0.10'
TEST_URL = 'http://ai.example.ts.net:11434'


class FakeResponse:
    def __init__(self, data, status=200):
        self.status_code = status
        self._data = data
        self.text = json.dumps(data)

    def json(self):
        return self._data


def configure(env, url=TEST_URL, model='test-model'):
    ICP = env['ir.config_parameter'].sudo()
    ICP.set_param('local_ai.url', url)
    ICP.set_param('local_ai.model', model)
    ICP.set_param('local_ai.tailscale_only', 'True')


@contextmanager
def fake_ollama(answers, address=TAILSCALE_ADDRESS):
    """Fake Ollama server: each /api/chat call returns the next answer of
    ``answers`` (a string, or a callable(payload) returning a string).
    Yields the list of the chat payloads received."""
    answers = list(answers)
    calls = []

    def request(method, url, json=None, timeout=None):
        if url.endswith('/api/version'):
            return FakeResponse({'version': 'test'})
        if url.endswith('/api/tags'):
            return FakeResponse({'models': [{'name': 'test-model'}]})
        calls.append(json)
        answer = answers.pop(0) if answers else 'OK'
        if callable(answer):
            answer = answer(json)
        return FakeResponse({'message': {'role': 'assistant', 'content': answer},
                             'prompt_eval_count': 10, 'eval_count': 5})

    with patch(RESOLVE, return_value=[address]), patch(REQUEST, side_effect=request):
        yield calls
