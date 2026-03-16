# -*- coding: utf-8 -*-
from odoo import models, fields, api


class HrAppraisalRequestWizard(models.TransientModel):
    _name = 'hr.appraisal.request.wizard'
    _description = 'Request Appraisal Wizard'

    employee_ids = fields.Many2many('hr.employee', string='Employees', required=True)
    template_id = fields.Many2one('hr.appraisal.template', string='Appraisal Template')
    date_open = fields.Date(string='Start Date', default=fields.Date.today, required=True)
    manager_id = fields.Many2one('hr.employee', string='Manager')

    def action_request_appraisal(self):
        appraisal_obj = self.env['hr.appraisal.custom']

        for employee in self.employee_ids:
            appraisal_obj.create({
                'employee_id': employee.id,
                'manager_id': self.manager_id.id if self.manager_id else employee.parent_id.id if employee.parent_id else False,
                'template_id': self.template_id.id if self.template_id else False,
                'date_open': self.date_open,
                'state': 'draft',
            })

        return {'type': 'ir.actions.act_window_close'}
