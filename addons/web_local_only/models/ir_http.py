# -*- coding: utf-8 -*-
from odoo import models


class IrHttp(models.AbstractModel):
    _inherit = 'ir.http'

    def session_info(self):
        info = super().session_info()
        # the "Support" entry of the user menu is removed; nothing else should point to odoo.com
        info['support_url'] = '/odoo'
        # AI of the editor: off unless a module answers it locally (local_ai sets it)
        info.setdefault('editor_ai_enabled', False)
        return info
