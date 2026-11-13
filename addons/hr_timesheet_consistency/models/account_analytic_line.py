# -*- coding: utf-8 -*-
from odoo import api, models

# Fields whose change can modify the hours logged on a day or their nature
CHECKED_FIELDS = {'date', 'unit_amount', 'employee_id', 'task_id', 'project_id', 'holiday_id', 'global_leave_id'}


class AccountAnalyticLine(models.Model):
    _inherit = 'account.analytic.line'

    @api.model_create_multi
    def create(self, vals_list):
        lines = super().create(vals_list)
        self.env['hr.timesheet.day.rules']._check_new_lines(lines)
        return lines

    def write(self, vals):
        """Check the days this write makes worse (see
        hr.timesheet.day.rules._raise_if_worse). Recomputations, e.g. when a
        task moves to another project, are not checked: they do not change
        what was logged. Odoo's own updates of the lines it generated for
        time off and public holidays (made as superuser) are not checked
        either."""
        if not CHECKED_FIELDS.intersection(vals):
            return super().write(vals)
        rules = self.env['hr.timesheet.day.rules']
        absence_task_ids = set(rules._get_absence_tasks().ids)
        timesheets = self.sudo().filtered(
            lambda line: line.project_id or vals.get('project_id') or vals.get('task_id'))
        if not timesheets or (self.env.su and all(
                rules._is_generated_absence(line, absence_task_ids) for line in timesheets)):
            return super().write(vals)
        pairs = rules._affected_days(timesheets, vals)
        rules._lock_employees(employee_id for employee_id, _day in pairs)
        before = rules._day_states(pairs, absence_task_ids)
        result = super().write(vals)
        if any(line.project_id for line in timesheets):
            after = rules._day_states(pairs, absence_task_ids)
            rules._raise_if_worse(pairs, before, after)
        return result
