# -*- coding: utf-8 -*-
from odoo import http
from odoo.http import request

from odoo.addons.web.controllers.session import Session


class LocalSession(Session):

    @http.route('/web/session/account', type='jsonrpc', auth='user', readonly=True)
    def account(self):
        """Local instance: no redirection to the odoo.com account."""
        return request.env['ir.config_parameter'].sudo().get_param('web.base.url', '') + '/odoo'
