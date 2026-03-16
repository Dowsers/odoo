# -*- coding: utf-8 -*-
from odoo import models, fields


class HrAppraisalObjective(models.Model):
    _name = 'hr.appraisal.objective'
    _description = 'Appraisal Objective'
    _order = 'sequence, id'

    appraisal_id = fields.Many2one('hr.appraisal.custom', string='Appraisal', required=True, ondelete='cascade')
    sequence = fields.Integer(string='Sequence', default=10)
    name = fields.Char(string='Objective', required=True)
    description = fields.Text(string='Description')
    objective_type = fields.Selection([
        ('past', 'Past'),
        ('future', 'Future'),
    ], string='Type', required=True, default='future')
    achievement = fields.Char(string='Achievement/Status')
    is_main_objective = fields.Boolean(string='Main Objective', default=False)
    deadline = fields.Date(string='Deadline')
    success_conditions = fields.Text(string='Success Conditions')
    manager_comment = fields.Text(string='Manager Comment')
    notes = fields.Text(string='Notes')
