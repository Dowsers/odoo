# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from dateutil.relativedelta import relativedelta


class HrAppraisalCustom(models.Model):
    _name = 'hr.appraisal.custom'
    _description = 'Employee Appraisal'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'date_open desc, id desc'

    name = fields.Char(string='Name', compute='_compute_name', store=True)
    display_name = fields.Char(compute='_compute_display_name', store=True)
    employee_id = fields.Many2one('hr.employee', string='Employee', required=True, tracking=True)
    manager_id = fields.Many2one('hr.employee', string='Manager', tracking=True)
    department_id = fields.Many2one('hr.department', string='Department', related='employee_id.department_id', store=True)
    job_id = fields.Many2one('hr.job', string='Job Position', related='employee_id.job_id', store=True)
    company_id = fields.Many2one('res.company', string='Company', default=lambda self: self.env.company)
    template_id = fields.Many2one('hr.appraisal.template', string='Appraisal Template')

    state = fields.Selection([
        ('draft', 'Draft'),
        ('in_progress', 'In Progress'),
        ('self_assessment', 'Self Assessment'),
        ('manager_assessment', 'Manager Assessment'),
        ('pending_signature', 'Pending Signature'),
        ('done', 'Done'),
        ('cancel', 'Cancelled'),
    ], string='Status', default='draft', required=True, tracking=True)

    date_open = fields.Date(string='Start Date', tracking=True)
    date_close = fields.Date(string='End Date', tracking=True)
    meeting_date = fields.Datetime(string='Meeting Date')
    meeting_id = fields.Many2one('calendar.event', string='Meeting')

    # Assessment fields
    self_assessment = fields.Text(string='Self Assessment')
    employee_feedback = fields.Text(string='Employee Feedback')
    manager_assessment = fields.Text(string='Manager Assessment')
    manager_feedback = fields.Text(string='Manager Feedback')

    strengths = fields.Text(string='Strengths')
    areas_improvement = fields.Text(string='Areas for Improvement')
    notes = fields.Text(string='Notes')

    overall_rating = fields.Selection([
        ('1', 'Unsatisfactory'),
        ('2', 'Needs Improvement'),
        ('3', 'Meets Expectations'),
        ('4', 'Exceeds Expectations'),
        ('5', 'Exceptional'),
    ], string='Overall Rating', tracking=True)

    overall_score = fields.Float(string='Overall Score', compute='_compute_overall_score', store=True)

    # Criteria and goals
    criteria_ids = fields.One2many('hr.appraisal.criteria.line', 'appraisal_id', string='Criteria')
    goal_ids = fields.One2many('hr.appraisal.goal', 'appraisal_id', string='Goals')
    objective_past_ids = fields.One2many('hr.appraisal.objective', 'appraisal_id', string='Past Objectives',
                                          domain=[('objective_type', '=', 'past')])
    objective_future_ids = fields.One2many('hr.appraisal.objective', 'appraisal_id', string='Future Objectives',
                                            domain=[('objective_type', '=', 'future')])
    key_competency_ids = fields.One2many('hr.appraisal.competency', 'appraisal_id', string='Key Competencies')
    technical_competency_ids = fields.One2many('hr.appraisal.competency', 'appraisal_id', string='Technical Competencies',
                                                domain=[('competency_type', '=', 'technical')])
    soft_skill_competency_ids = fields.One2many('hr.appraisal.competency', 'appraisal_id', string='Soft Skills',
                                                 domain=[('competency_type', '=', 'soft_skill')])
    leadership_competency_ids = fields.One2many('hr.appraisal.competency', 'appraisal_id', string='Leadership',
                                                 domain=[('competency_type', '=', 'leadership')])

    # Additional fields
    evaluator_id = fields.Many2one('hr.employee', string='Evaluator')
    evaluator_name = fields.Char(string='Evaluator Name')
    evaluator_function = fields.Char(string='Evaluator Function')
    evaluator_phone = fields.Char(string='Evaluator Phone')
    appraisal_year = fields.Char(string='Appraisal Year')
    site = fields.Char(string='Site')

    interview_date = fields.Date(string='Interview Date')
    interview_time = fields.Char(string='Interview Time')
    interview_notes = fields.Text(string='Interview Notes')

    workload_remarks = fields.Selection([
        ('yes', 'Yes'),
        ('no', 'No'),
    ], string='Workload Remarks')
    workload_notes = fields.Text(string='Workload Notes')

    remuneration_remarks = fields.Selection([
        ('yes', 'Yes'),
        ('no', 'No'),
    ], string='Remuneration Remarks')
    remuneration_notes = fields.Text(string='Remuneration Notes')

    global_performance = fields.Selection([
        ('unsatisfactory', 'Unsatisfactory'),
        ('below_expectations', 'Below Expectations'),
        ('meets_expectations', 'Meets Expectations'),
        ('above_expectations', 'Above Expectations'),
        ('exceptional', 'Exceptional'),
    ], string='Global Performance')
    global_performance_comment = fields.Text(string='Global Performance Comment')
    global_performance_notes = fields.Text(string='Global Performance Notes')

    evaluator_acknowledgment = fields.Selection([
        ('pending', 'Pending'),
        ('acknowledged', 'Acknowledged'),
    ], string='Evaluator Acknowledgment')
    evaluator_date = fields.Date(string='Evaluator Signature Date')
    evaluator_signature = fields.Binary(string='Evaluator Signature', attachment=True)
    evaluator_comment = fields.Text(string='Evaluator Comment')

    employee_acknowledgment = fields.Selection([
        ('pending', 'Pending'),
        ('acknowledged', 'Acknowledged'),
    ], string='Employee Acknowledgment')
    employee_date = fields.Date(string='Employee Signature Date')
    employee_signature = fields.Binary(string='Employee Signature', attachment=True)
    employee_comment = fields.Text(string='Employee Comment')

    attachment_ids = fields.Many2many('ir.attachment', string='Attachments')
    attachment_notes = fields.Text(string='Attachment Notes')

    @api.depends('employee_id', 'date_open')
    def _compute_name(self):
        for record in self:
            if record.employee_id and record.date_open:
                record.name = f'{record.employee_id.name} - {record.date_open}'
            elif record.employee_id:
                record.name = record.employee_id.name
            else:
                record.name = _('New Appraisal')

    @api.depends('name')
    def _compute_display_name(self):
        for record in self:
            record.display_name = record.name

    @api.depends('criteria_ids.score', 'criteria_ids.weight')
    def _compute_overall_score(self):
        for record in self:
            total_weight = sum(record.criteria_ids.mapped('weight'))
            if total_weight > 0:
                weighted_scores = sum(c.score * c.weight for c in record.criteria_ids if c.score and c.weight)
                record.overall_score = weighted_scores / total_weight
            else:
                record.overall_score = 0.0

    def action_start(self):
        self.write({'state': 'in_progress', 'date_open': fields.Date.today()})

    def action_self_assessment(self):
        self.write({'state': 'self_assessment'})

    def action_manager_assessment(self):
        self.write({'state': 'manager_assessment'})

    def action_pending_signature(self):
        self.write({'state': 'pending_signature'})

    def action_done(self):
        self.write({'state': 'done', 'date_close': fields.Date.today()})

    def action_cancel(self):
        self.write({'state': 'cancel'})

    def action_reset_to_draft(self):
        self.write({'state': 'draft'})

    def action_reset_draft(self):
        """Alias for action_reset_to_draft for backwards compatibility"""
        return self.action_reset_to_draft()

    def action_load_dowsers_template(self):
        """Load the Dowsers template into this appraisal"""
        self.ensure_one()
        # Find the template - try to find one with "Dowsers" in name, or use the first one
        template = self.env['hr.appraisal.template'].search([
            ('name', 'ilike', 'dowsers')
        ], limit=1)
        if not template:
            # Fall back to any template
            template = self.env['hr.appraisal.template'].search([], limit=1)

        if template:
            self.template_id = template.id
            # Load criteria from template if available
            if template.criteria_ids:
                # Remove existing criteria
                self.criteria_ids.unlink()
                # Create new criteria from template
                for template_criteria in template.criteria_ids:
                    self.env['hr.appraisal.criteria.line'].create({
                        'appraisal_id': self.id,
                        'name': template_criteria.name,
                        'category': template_criteria.category,
                        'description': template_criteria.description,
                        'weight': template_criteria.weight,
                        'sequence': template_criteria.sequence,
                    })
        return True

    def action_schedule_meeting(self):
        """Schedule a calendar meeting for this appraisal"""
        self.ensure_one()
        # Create or update calendar event
        if not self.meeting_id:
            meeting = self.env['calendar.event'].create({
                'name': f'Appraisal Meeting - {self.employee_id.name}',
                'start': self.meeting_date or fields.Datetime.now(),
                'stop': (self.meeting_date or fields.Datetime.now()) + relativedelta(hours=1),
                'partner_ids': [(6, 0, [
                    self.employee_id.user_id.partner_id.id,
                    self.manager_id.user_id.partner_id.id if self.manager_id and self.manager_id.user_id else False,
                ])],
                'description': f'Performance appraisal meeting for {self.employee_id.name}',
            })
            self.meeting_id = meeting.id
        # Return action to open the meeting
        return {
            'type': 'ir.actions.act_window',
            'name': 'Appraisal Meeting',
            'res_model': 'calendar.event',
            'res_id': self.meeting_id.id,
            'view_mode': 'form',
            'target': 'new',
        }
