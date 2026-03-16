# -*- coding: utf-8 -*-
from odoo import models, fields, api
from dateutil.relativedelta import relativedelta


class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    appraisal_ids = fields.One2many('hr.appraisal.custom', 'employee_id', string='Appraisals', groups='base.group_user')
    appraisal_count = fields.Integer(string='Appraisal Count', compute='_compute_appraisal_count', groups='base.group_user')
    appraisal_enabled = fields.Boolean(string='Appraisal Enabled', default=True, groups='base.group_user')
    appraisal_date = fields.Date(string='Appraisal Date', groups='base.group_user')
    last_appraisal_date = fields.Date(string='Last Appraisal Date', compute='_compute_last_appraisal_date', store=True, groups='base.group_user')
    last_appraisal_rating = fields.Selection([
        ('1', 'Unsatisfactory'),
        ('2', 'Needs Improvement'),
        ('3', 'Meets Expectations'),
        ('4', 'Exceeds Expectations'),
        ('5', 'Exceptional'),
    ], string='Last Appraisal Rating', compute='_compute_last_appraisal_rating', store=True, groups='base.group_user')
    next_appraisal_date = fields.Date(string='Next Appraisal Date', groups='base.group_user')
    appraisal_frequency = fields.Selection([
        ('monthly', 'Monthly'),
        ('quarterly', 'Quarterly'),
        ('semi_annually', 'Semi-Annually'),
        ('annually', 'Annually'),
    ], string='Appraisal Frequency', default='annually', groups='base.group_user')

    def _compute_appraisal_count(self):
        for employee in self:
            employee.appraisal_count = len(employee.appraisal_ids)

    @api.depends('appraisal_ids.date_close', 'appraisal_ids.overall_rating')
    def _compute_last_appraisal_date(self):
        for employee in self:
            closed_appraisals = employee.appraisal_ids.filtered(lambda a: a.state == 'done' and a.date_close)
            if closed_appraisals:
                employee.last_appraisal_date = max(closed_appraisals.mapped('date_close'))
            else:
                employee.last_appraisal_date = False

    @api.depends('appraisal_ids.date_close', 'appraisal_ids.overall_rating')
    def _compute_last_appraisal_rating(self):
        for employee in self:
            closed_appraisals = employee.appraisal_ids.filtered(lambda a: a.state == 'done' and a.date_close and a.overall_rating)
            if closed_appraisals:
                # Get the most recent appraisal
                latest_appraisal = closed_appraisals.sorted('date_close', reverse=True)[0]
                employee.last_appraisal_rating = latest_appraisal.overall_rating
            else:
                employee.last_appraisal_rating = False

    def action_view_appraisals(self):
        self.ensure_one()
        action = self.env.ref('hr_appraisal_custom.action_hr_appraisal_from_employee').read()[0]
        action['domain'] = [('employee_id', '=', self.id)]
        action['context'] = {'default_employee_id': self.id}
        return action

    def _cron_schedule_appraisals(self):
        """
        Scheduled action to create appraisals for employees based on their next appraisal date.
        This method is called by the cron job 'Schedule Periodic Appraisals'.
        """
        today = fields.Date.today()
        employees = self.search([
            ('next_appraisal_date', '<=', today),
            ('next_appraisal_date', '!=', False),
            ('active', '=', True),
        ])

        appraisal_obj = self.env['hr.appraisal.custom']

        for employee in employees:
            # Check if there's already a draft or in-progress appraisal
            existing_appraisal = appraisal_obj.search([
                ('employee_id', '=', employee.id),
                ('state', 'in', ['draft', 'in_progress', 'self_assessment', 'manager_assessment']),
            ], limit=1)

            if not existing_appraisal:
                # Create new appraisal
                appraisal_obj.create({
                    'employee_id': employee.id,
                    'manager_id': employee.parent_id.id if employee.parent_id else False,
                    'department_id': employee.department_id.id if employee.department_id else False,
                    'job_id': employee.job_id.id if employee.job_id else False,
                    'company_id': employee.company_id.id,
                    'date_open': today,
                    'state': 'draft',
                })

                # Update next appraisal date based on frequency
                if employee.appraisal_frequency == 'monthly':
                    employee.next_appraisal_date = today + relativedelta(months=1)
                elif employee.appraisal_frequency == 'quarterly':
                    employee.next_appraisal_date = today + relativedelta(months=3)
                elif employee.appraisal_frequency == 'semi_annually':
                    employee.next_appraisal_date = today + relativedelta(months=6)
                else:  # annually
                    employee.next_appraisal_date = today + relativedelta(years=1)

        return True
