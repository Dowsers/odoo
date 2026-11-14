# -*- coding: utf-8 -*-
from odoo import api, fields, models

from .hr_public_holiday_fr import COUNTRY_ZONES, CRON_XMLID, ZONES


class ResCompany(models.Model):
    _inherit = 'res.company'

    fr_public_holidays_zone = fields.Selection(
        ZONES, string='Official Public Holidays',
        compute='_compute_fr_public_holidays_zone', store=True, readonly=False,
        help="Zone whose official public holidays, published by the government on calendrier.api.gouv.fr, "
             "are imported every week into the public holidays of the company. Leave empty to stop the import.")
    fr_public_holidays_sync_date = fields.Datetime(
        string='Public Holidays Imported On', readonly=True, copy=False)
    fr_public_holidays_sync_error = fields.Char(
        string='Public Holidays Import Error', readonly=True, copy=False)

    @api.depends('partner_id.country_id')
    def _compute_fr_public_holidays_zone(self):
        for company in self:
            company.fr_public_holidays_zone = COUNTRY_ZONES.get(company.partner_id.country_id.code or '', False)

    def write(self, vals):
        zone_changed = 'fr_public_holidays_zone' in vals and any(
            company.fr_public_holidays_zone != vals['fr_public_holidays_zone'] for company in self)
        result = super().write(vals)
        if zone_changed and vals['fr_public_holidays_zone']:
            cron = self.env.ref(CRON_XMLID, raise_if_not_found=False)
            if cron:
                cron.sudo()._trigger()
        return result
