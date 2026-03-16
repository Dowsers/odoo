# -*- coding: utf-8 -*-
from odoo import models, fields


class HrAppraisalGoal(models.Model):
    _name = 'hr.appraisal.goal'
    _description = 'Appraisal Goal'
    _order = 'deadline, id'

    appraisal_id = fields.Many2one('hr.appraisal.custom', string='Appraisal', required=True, ondelete='cascade')
    name = fields.Char(string='Goal', required=True)
    description = fields.Text(string='Description')
    deadline = fields.Date(string='Deadline')
    state = fields.Selection([
        ('not_started', 'Not Started'),
        ('in_progress', 'In Progress'),
        ('achieved', 'Achieved'),
        ('not_achieved', 'Not Achieved'),
    ], string='Status', default='not_started')
    progress = fields.Selection([
        ('0', '0%'),
        ('25', '25%'),
        ('50', '50%'),
        ('75', '75%'),
        ('100', '100%'),
    ], string='Progress')
    notes = fields.Text(string='Notes')
