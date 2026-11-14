# -*- coding: utf-8 -*-
from odoo import api, models

from .hr_public_holiday_fr import API_SOURCE


class TimesheetDayRules(models.AbstractModel):
    _inherit = 'hr.timesheet.day.rules'

    @api.model
    def _get_reference_public_holidays(self, year, employee=None):
        """Once the official public holidays of the year have been imported,
        the public holidays of Odoo are the only reference: the timesheet rules
        then follow exactly what Time Off uses, including a public holiday
        deleted or added by hand. The computed French public holidays remain
        for the years not imported."""
        companies = employee.sudo().company_id if employee else self.env.companies
        if self.env['hr.public.holiday.fr']._is_year_imported(year, companies):
            return {}
        return super()._get_reference_public_holidays(year, employee)

    @api.model
    def _get_public_holiday_source(self, leave):
        if leave.sudo().fr_official_holiday_ids.filtered(lambda row: row.state == 'imported'):
            return API_SOURCE
        return super()._get_public_holiday_source(leave)
