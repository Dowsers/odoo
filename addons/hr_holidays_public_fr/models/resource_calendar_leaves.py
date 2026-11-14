# -*- coding: utf-8 -*-
from odoo import api, fields, models

from .hr_public_holiday_fr import TIMESHEETS_FROM_KEY


class ResourceCalendarLeaves(models.Model):
    _inherit = 'resource.calendar.leaves'

    fr_official_holiday_ids = fields.One2many(
        'hr.public.holiday.fr', 'leave_id', string='Official Public Holidays', readonly=True)

    def _generate_timesheeets(self):
        """The import of the official public holidays generates no timesheet
        for the days already past: employees have filled these days already
        (like Odoo, which only generates the upcoming public holidays for a
        new employee)."""
        timesheets_from = self.env.context.get(TIMESHEETS_FROM_KEY)
        leaves = self
        if timesheets_from:
            limit = fields.Datetime.to_datetime(timesheets_from)
            leaves = self.filtered(lambda leave: leave.date_to >= limit)
        return super(ResourceCalendarLeaves, leaves)._generate_timesheeets()

    def _get_overlapping_hr_leaves(self, domain=None):
        """Timesheets only exist for validated time off. Without this filter,
        deleting or moving a public holiday makes Odoo generate timesheets
        for the pending and refused requests that overlap it as well."""
        return super()._get_overlapping_hr_leaves(list(domain or []) + [('state', '=', 'validate')])

    def unlink(self):
        # remember the imported public holidays deleted in Odoo: they are not imported again
        self.env['hr.public.holiday.fr'].sudo().search([
            ('leave_id', 'in', self.ids), ('state', '=', 'imported'),
        ]).write({'state': 'deleted'})
        return super().unlink()

    @api.model
    def action_import_fr_public_holidays(self):
        """Button of the public holidays list."""
        return self.env['hr.public.holiday.fr']._action_import(self.env.companies)
