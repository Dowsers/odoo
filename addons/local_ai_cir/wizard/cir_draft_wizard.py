# -*- coding: utf-8 -*-
from datetime import date

from odoo import _, api, fields, models
from odoo.exceptions import UserError

from ..models.cir_draft import ADMIN_GROUP


class LocalAICirDraftWizard(models.TransientModel):
    _name = 'local.ai.cir.draft.wizard'
    _description = 'Prepare the CIR dossier drafts'

    @api.model
    def _year_selection(self):
        year = fields.Date.context_today(self).year
        return [(str(value), str(value)) for value in range(year - 3, year + 1)]

    year = fields.Selection(selection='_year_selection', required=True,
                            default=lambda self: str(fields.Date.context_today(self).year))
    task_ids = fields.Many2many('project.task', string='R&D Tasks', compute='_compute_task_ids', store=True,
                                readonly=False,
                                help="By default, the tasks with activity timesheets in the year, the most worked "
                                     "first. Remove the tasks that are not R&D operations.")

    @api.depends('year')
    def _compute_task_ids(self):
        absence_ids = self.env['hr.timesheet.day.rules']._get_absence_tasks().ids
        for wizard in self:
            if not wizard.year:
                wizard.task_ids = False
                continue
            year = int(wizard.year)
            groups = self.env['account.analytic.line']._read_group(
                [('project_id', '!=', False), ('task_id', '!=', False), ('task_id', 'not in', absence_ids),
                 ('date', '>=', date(year, 1, 1)), ('date', '<=', date(year, 12, 31))],
                ['task_id'], ['unit_amount:sum'])
            wizard.task_ids = [task.id for task, hours in sorted(groups, key=lambda group: -group[1]) if hours > 0]

    def action_generate(self):
        self.ensure_one()
        if not self.env.user.has_group(ADMIN_GROUP):
            raise UserError(_("Only timesheet administrators can prepare the CIR dossier."))
        if not self.task_ids:
            raise UserError(_("Select at least one task."))
        Draft = self.env['local.ai.cir.draft']
        year = int(self.year)
        existing = Draft.search([('year', '=', year), ('task_id', 'in', self.task_ids.ids)])
        missing = self.task_ids - existing.task_id
        drafts = existing | Draft.create([{'year': year, 'task_id': task.id} for task in missing])
        drafts._local_ai_enqueue()
        return {
            'type': 'ir.actions.act_window',
            'name': _("CIR Dossier %s (AI Drafts)", year),
            'res_model': 'local.ai.cir.draft',
            'view_mode': 'list,form',
            'domain': [('year', '=', year)],
            'context': {'search_default_group_project': 1},
        }
