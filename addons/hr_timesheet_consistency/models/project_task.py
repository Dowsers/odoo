# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import AccessError

from .timesheet_day_rules import ADMIN_GROUP, is_absence_name


class ProjectTask(models.Model):
    _inherit = 'project.task'

    timesheet_absence = fields.Boolean(
        string='Absence (timesheets)',
        compute='_compute_timesheet_absence', store=True, readonly=False, copy=False,
        help="Timesheets on this task record an absence (leave, public holiday, RTT...), not an activity: "
             "they are allowed on public holidays and reported on the \"Absence / Congés\" row of the CIR "
             "export. Only timesheet administrators can change it. When they create a task, it is set from "
             "the name (congé, férié, time off, absence, RTT, maladie, vacances); renaming the task does not "
             "change it.")

    @api.depends()
    def _compute_timesheet_absence(self):
        # Initial value of the tasks existing when the module is installed;
        # no dependency, so that renaming a task does not change it.
        for task in self:
            task.timesheet_absence = is_absence_name(task.name)

    def _check_timesheet_absence_rights(self):
        if not self.env.su and not self.env.user.has_group(ADMIN_GROUP):
            raise AccessError(_("Only timesheet administrators can mark a task as an absence."))

    @api.model_create_multi
    def create(self, vals_list):
        if any('timesheet_absence' in vals for vals in vals_list):
            self._check_timesheet_absence_rights()
        tasks = super().create(vals_list)
        if self.env.su or self.env.user.has_group(ADMIN_GROUP):
            # default value from the name, for the tasks created by timesheet administrators
            to_flag = [task.id for task, vals in zip(tasks, vals_list)
                       if 'timesheet_absence' not in vals and is_absence_name(task.name)]
            self.browse(to_flag).sudo().write({'timesheet_absence': True})
        return tasks

    def write(self, vals):
        if 'timesheet_absence' in vals:
            self._check_timesheet_absence_rights()
        return super().write(vals)

    def copy(self, default=None):
        copies = super().copy(default)
        for task, copy in zip(self.sudo(), copies.sudo()):
            if task.timesheet_absence and not copy.timesheet_absence:
                copy.timesheet_absence = True
        return copies
