# -*- coding: utf-8 -*-
from odoo import models


class IrHttp(models.AbstractModel):
    _inherit = 'ir.http'

    def session_info(self):
        info = super().session_info()
        # read by web_local_only and by this module's editor plugin
        info['editor_ai_enabled'] = bool(self.env.user._is_internal() and self.env['local.ai']._is_enabled())
        return info
