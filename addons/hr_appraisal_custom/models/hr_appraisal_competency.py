# -*- coding: utf-8 -*-
from odoo import models, fields


class HrAppraisalCompetency(models.Model):
    _name = 'hr.appraisal.competency'
    _description = 'Appraisal Competency'
    _order = 'sequence, id'

    appraisal_id = fields.Many2one('hr.appraisal.custom', string='Appraisal', required=True, ondelete='cascade')
    sequence = fields.Integer(string='Sequence', default=10)
    name = fields.Char(string='Competency', required=True)
    description = fields.Text(string='Description')
    competency_type = fields.Selection([
        ('technical', 'Technical'),
        ('soft_skill', 'Soft Skill'),
        ('leadership', 'Leadership'),
        ('other', 'Other'),
    ], string='Type')
    level = fields.Selection([
        ('beginner', 'Beginner'),
        ('intermediate', 'Intermediate'),
        ('advanced', 'Advanced'),
        ('expert', 'Expert'),
    ], string='Level')
    mastery_level = fields.Selection([
        ('1', 'Developing'),
        ('2', 'Competent'),
        ('3', 'Proficient'),
        ('4', 'Expert'),
    ], string='Mastery Level')
    comment = fields.Text(string='Comment')
    notes = fields.Text(string='Notes')
