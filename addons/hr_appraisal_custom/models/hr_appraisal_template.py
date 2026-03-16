# -*- coding: utf-8 -*-
from odoo import models, fields


class HrAppraisalTemplate(models.Model):
    _name = 'hr.appraisal.template'
    _description = 'Appraisal Template'
    _order = 'name'

    name = fields.Char(string='Template Name', required=True)
    description = fields.Text(string='Description')
    active = fields.Boolean(string='Active', default=True)
    company_id = fields.Many2one('res.company', string='Company', default=lambda self: self.env.company)
    criteria_ids = fields.One2many('hr.appraisal.template.criteria', 'template_id', string='Criteria')


class HrAppraisalTemplateCriteria(models.Model):
    _name = 'hr.appraisal.template.criteria'
    _description = 'Appraisal Template Criteria'
    _order = 'sequence, id'

    template_id = fields.Many2one('hr.appraisal.template', string='Template', required=True, ondelete='cascade')
    sequence = fields.Integer(string='Sequence', default=10)
    name = fields.Char(string='Criteria Name', required=True)
    description = fields.Text(string='Description')
    category = fields.Char(string='Category')
    weight = fields.Float(string='Weight', default=1.0)
