# -*- coding: utf-8 -*-
from odoo import api, fields, models

from odoo.addons.hr_timesheet_consistency.models.timesheet_day_rules import WHIT_MONDAY_PARAM

from .hr_public_holiday_fr import CRON_XMLID


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    fr_public_holidays_zone = fields.Selection(related='company_id.fr_public_holidays_zone', readonly=False)
    fr_public_holidays_sync_date = fields.Datetime(related='company_id.fr_public_holidays_sync_date')
    fr_public_holidays_sync_error = fields.Char(related='company_id.fr_public_holidays_sync_error')
    fr_whit_monday_worked = fields.Boolean(
        string='Whit Monday Is a Worked Day',
        help="Journée de solidarité: the upcoming Whit Mondays are not imported as public holidays, "
             "and activities can be logged on them. Past days are never changed.")

    @api.model
    def get_values(self):
        res = super().get_values()
        res['fr_whit_monday_worked'] = self.env['hr.timesheet.day.rules']._whit_monday_worked()
        return res

    def set_values(self):
        super().set_values()
        self._set_fr_whit_monday_worked()

    def _set_fr_whit_monday_worked(self):
        # stored as "True" / "False": an empty parameter means "worked"
        if self.fr_whit_monday_worked != self.env['hr.timesheet.day.rules']._whit_monday_worked():
            self.env['ir.config_parameter'].sudo().set_param(
                WHIT_MONDAY_PARAM, 'True' if self.fr_whit_monday_worked else 'False')
            cron = self.env.ref(CRON_XMLID, raise_if_not_found=False)
            if cron:
                cron.sudo()._trigger()

    def action_import_fr_public_holidays(self):
        self.ensure_one()
        # a button does not save the settings: apply the Whit Monday choice first
        self._set_fr_whit_monday_worked()
        return self.env['hr.public.holiday.fr']._action_import(self.company_id)
