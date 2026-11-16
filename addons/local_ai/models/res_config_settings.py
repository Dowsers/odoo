# -*- coding: utf-8 -*-
from odoo import _, fields, models

from .local_ai import DEFAULT_MODEL, DEFAULT_TIMEOUT


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    local_ai_url = fields.Char(
        string='Ollama Server', config_parameter='local_ai.url',
        help="Address of the Ollama server, through Tailscale, e.g. http://machine.tailnet.ts.net:11434. "
             "Leave empty to disable the local AI.")
    local_ai_model = fields.Char(string='AI Model', config_parameter='local_ai.model', default=DEFAULT_MODEL)
    local_ai_timeout = fields.Integer(string='AI Timeout (s)', config_parameter='local_ai.timeout',
                                      default=DEFAULT_TIMEOUT)

    def action_local_ai_test(self):
        self.ensure_one()
        self.execute()
        message = self.env['local.ai']._test_connection()
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {'type': 'success', 'title': _("Local AI"), 'message': message, 'sticky': False},
        }
