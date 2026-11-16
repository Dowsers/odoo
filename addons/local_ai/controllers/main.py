# -*- coding: utf-8 -*-
import babel

from odoo import _, http
from odoo.http import request
from odoo.tools import html2plaintext, plaintext2html

from odoo.addons.html_editor.controllers.main import HTML_Editor
from odoo.addons.mail.controllers.google_translate import GoogleTranslateController

from ..models.local_ai import LocalAIError

MAX_PROMPT = 8000
MAX_HISTORY = 12

TRANSLATE_SYSTEM = (
    "Tu es un traducteur professionnel. Tu traduis fidèlement le texte fourni, sans rien ajouter "
    "ni commenter, en conservant les retours à la ligne. Réponds uniquement par la traduction."
)


class LocalAIEditor(HTML_Editor):

    @http.route(["/web_editor/generate_text", "/html_editor/generate_text"], type="jsonrpc", auth="user")
    def generate_text(self, prompt, conversation_history):
        """The editor's AI requests (translation, writing assistant) are
        answered by the local AI server."""
        LocalAI = request.env['local.ai']
        if not LocalAI._is_enabled() or not request.env.user._is_internal():
            return super().generate_text(prompt, conversation_history)
        history = [
            {'role': message['role'], 'content': message['content'][:MAX_PROMPT]}
            for message in (conversation_history or [])
            if isinstance(message, dict) and message.get('role') in ('system', 'user', 'assistant')
            and isinstance(message.get('content'), str)
        ]
        system = [message for message in history if message['role'] == 'system'][:1]
        others = [message for message in history if message['role'] != 'system'][-MAX_HISTORY:]
        messages = system + others + [{'role': 'user', 'content': str(prompt or '')[:MAX_PROMPT]}]
        return LocalAI._chat(messages, temperature=0.3)


class LocalAITranslate(GoogleTranslateController):

    @http.route("/mail/message/translate", type="jsonrpc", auth="user")
    def translate(self, message_id):
        """Translation of a chatter message by the local AI when no Google
        Translate key is configured."""
        get_param = request.env["ir.config_parameter"].sudo().get_param
        LocalAI = request.env['local.ai']
        if get_param("mail.google_translate_api_key") or not LocalAI._is_enabled():
            return super().translate(message_id)
        message = request.env["mail.message"].search([("id", "=", message_id)])
        if not message:
            raise request.not_found()
        target_lang = request.env.user.lang.split("_")[0]
        Translation = request.env["mail.message.translation"].sudo()
        translation = Translation.search([("message_id", "=", message.id), ("target_lang", "=", target_lang)])
        if not translation:
            text = html2plaintext(str(message.body or ''))[:MAX_PROMPT]
            target_name = babel.Locale.parse(target_lang).get_display_name('fr') if target_lang else target_lang
            try:
                source_lang = LocalAI._chat(
                    [{'role': 'user', 'content': (
                        "Quelle est la langue de ce texte ? Réponds uniquement par son code ISO 639-1 "
                        "en minuscules (par exemple fr, en, de).\n\n" + text[:1500])}],
                    temperature=0, max_tokens=5).strip().lower()[:2]
                if not source_lang.isalpha() or len(source_lang) != 2:
                    source_lang = 'und'
                translated = LocalAI._chat(
                    [{'role': 'user', 'content': "Traduis ce texte en %s :\n\n%s" % (target_name, text)}],
                    system=TRANSLATE_SYSTEM, temperature=0.1)
            except LocalAIError as error:
                return {"error": str(error.args[0] if error.args else error)}
            translation = Translation.create({
                "body": plaintext2html(translated),
                "message_id": message.id,
                "source_lang": source_lang,
                "target_lang": target_lang,
            })
        try:
            lang_name = babel.Locale(translation.source_lang).get_display_name(request.env.user.lang)
        except (babel.UnknownLocaleError, ValueError):
            lang_name = translation.source_lang
        return {"body": translation.body, "lang_name": lang_name}
