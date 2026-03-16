# -*- coding: utf-8 -*-
from odoo import models, fields, api


class HrAppraisalCriteriaLine(models.Model):
    _name = 'hr.appraisal.criteria.line'
    _description = 'Appraisal Criteria Line'
    _order = 'sequence, id'

    appraisal_id = fields.Many2one('hr.appraisal.custom', string='Appraisal', required=True, ondelete='cascade')
    sequence = fields.Integer(string='Sequence', default=10)
    name = fields.Char(string='Criteria', required=True)
    category = fields.Char(string='Category')
    description = fields.Text(string='Description')
    weight = fields.Float(string='Weight', default=1.0)

    self_rating = fields.Selection([
        ('1', '1 - Unsatisfactory'),
        ('2', '2 - Needs Improvement'),
        ('3', '3 - Meets Expectations'),
        ('4', '4 - Exceeds Expectations'),
        ('5', '5 - Exceptional'),
    ], string='Self Rating')
    self_comment = fields.Text(string='Self Comment')

    manager_rating = fields.Selection([
        ('1', '1 - Unsatisfactory'),
        ('2', '2 - Needs Improvement'),
        ('3', '3 - Meets Expectations'),
        ('4', '4 - Exceeds Expectations'),
        ('5', '5 - Exceptional'),
    ], string='Manager Rating')
    manager_comment = fields.Text(string='Manager Comment')

    score = fields.Float(string='Score', compute='_compute_score', store=True)

    @api.depends('manager_rating', 'self_rating')
    def _compute_score(self):
        for record in self:
            if record.manager_rating:
                record.score = float(record.manager_rating)
            elif record.self_rating:
                record.score = float(record.self_rating)
            else:
                record.score = 0.0
