# -*- coding: utf-8 -*-
from odoo import _, http
from odoo.exceptions import UserError

from odoo.addons.html_editor.controllers.main import HTML_Editor


class LocalEditor(HTML_Editor):

    @http.route(["/web_editor/generate_text", "/html_editor/generate_text"], type="jsonrpc", auth="user")
    def generate_text(self, prompt, conversation_history):
        """Local instance: the editor's AI requests are never sent to
        olg.api.odoo.com. A module may answer them locally (local_ai)."""
        raise UserError(_("The AI of the editor is not available on this instance."))
