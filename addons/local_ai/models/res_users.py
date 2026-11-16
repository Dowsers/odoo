# -*- coding: utf-8 -*-
from odoo import models


class ResUsers(models.Model):
    _inherit = 'res.users'

    def _init_store_data(self, store):
        super()._init_store_data(store)
        # "Translate" action of the chatter messages, answered by the local AI
        # when no Google Translate key is configured
        get_param = self.env['ir.config_parameter'].sudo().get_param
        if self.env.user._is_internal() and not get_param('mail.google_translate_api_key') \
                and self.env['local.ai']._is_enabled():
            store.add_global_values(hasMessageTranslationFeature=True)
