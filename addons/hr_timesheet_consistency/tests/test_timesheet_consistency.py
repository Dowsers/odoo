# -*- coding: utf-8 -*-
from contextlib import contextmanager
from datetime import date, datetime

from odoo.exceptions import ValidationError
from odoo.tests import TransactionCase, tagged

from ..models.timesheet_day_rules import WHIT_MONDAY_PARAM, easter_date, french_public_holidays, is_absence_name

USER_GROUP = 'hr_timesheet.group_hr_timesheet_user'
ADMIN_GROUP = 'hr_timesheet.group_timesheet_manager'


@tagged('post_install', '-at_install')
class TestTimesheetConsistency(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env = cls.env(context=dict(cls.env.context, tracking_disable=True, no_reset_password=True))
        # A company of its own: the tests do not depend on the public holidays, time off and
        # settings of the database (e.g. public holidays imported by hr_holidays_public_fr).
        cls.company = cls.env['res.company'].create({'name': 'Consistency Company'})
        cls.env = cls.env(context=dict(cls.env.context, allowed_company_ids=cls.company.ids))
        cls.company.timesheet_encode_uom_id = cls.env.ref('uom.product_uom_day')
        cls.env['ir.config_parameter'].sudo().set_param(WHIT_MONDAY_PARAM, 'True')
        cls.calendar = cls.env['resource.calendar'].create({
            'name': 'Consistency 40h', 'hours_per_day': 8.0, 'tz': 'Europe/Paris', 'company_id': cls.company.id,
        })
        base_user = cls.env.ref('base.group_user')
        cls.user = cls.env['res.users'].create({
            'name': 'Consistency User', 'login': 'consistency_user', 'email': 'consistency_user@example.com',
            'tz': 'Europe/Paris', 'group_ids': [(6, 0, [base_user.id, cls.env.ref(USER_GROUP).id])],
        })
        cls.admin = cls.env['res.users'].create({
            'name': 'Consistency Admin', 'login': 'consistency_admin', 'email': 'consistency_admin@example.com',
            'tz': 'Europe/Paris',
            'group_ids': [(6, 0, [base_user.id, cls.env.ref(ADMIN_GROUP).id, cls.env.ref('project.group_project_user').id])],
        })
        Employee = cls.env['hr.employee']
        common = {'resource_calendar_id': cls.calendar.id, 'company_id': cls.company.id}
        cls.employee = Employee.create(dict(common, name='Consistency Employee', user_id=cls.user.id))
        cls.admin_employee = Employee.create(dict(common, name='Consistency Admin Employee', user_id=cls.admin.id))
        cls.other_employee = Employee.create(dict(common, name='Other Employee'))
        plan = cls.env['account.analytic.plan'].create({'name': 'Consistency plan'})
        Project = cls.env['project.project']
        cls.project, cls.other_project = [Project.create({
            'name': name, 'allow_timesheets': True, 'privacy_visibility': 'employees', 'company_id': cls.company.id,
            'account_id': cls.env['account.analytic.account'].create({
                'name': name, 'plan_id': plan.id, 'company_id': cls.company.id}).id,
        }) for name in ('Consistency Project', 'Other Project')]
        Task = cls.env['project.task']
        cls.task_work = Task.create({'name': 'Développement', 'project_id': cls.project.id})
        cls.task_review = Task.create({'name': 'Relecture', 'project_id': cls.project.id})
        cls.task_leave = Task.create({'name': 'Congés', 'project_id': cls.project.id})
        cls.task_rtt = Task.create({'name': 'RTT', 'project_id': cls.project.id})
        cls.rules = cls.env['hr.timesheet.day.rules']

    def _log(self, day, hours, task=None, user=None, employee=None):
        Line = self.env['account.analytic.line'].with_user(user or self.user)
        return Line.create({
            'name': '/',
            'date': day,
            'unit_amount': hours,
            'project_id': (task or self.task_work).project_id.id,
            'task_id': (task or self.task_work).id,
            'employee_id': (employee or self.employee).id,
        })

    @contextmanager
    def assertRefused(self, message=None):
        """assertRaises(ValidationError), which rolls the refused operation
        back, plus a check of the message."""
        with self.assertRaises(ValidationError) as context:
            yield context
        if message:
            self.assertIn(message, str(context.exception))

    def _legacy(self, line, **values):
        """Change a line in SQL, like data entered before the module."""
        for name, value in values.items():
            self.env.cr.execute(
                'UPDATE account_analytic_line SET "%s" = %%s WHERE id = %%s' % name, (value, line.id))
        self.env.invalidate_all()

    def _state(self, employee, day):
        absence_ids = set(self.rules._get_absence_tasks().ids)
        return self.rules._day_states({(employee.id, day)}, absence_ids)[(employee.id, day)]

    def test_helpers(self):
        self.assertEqual(easter_date(2027), date(2027, 3, 28))
        holidays_2027 = dict(french_public_holidays(2027))
        self.assertEqual(holidays_2027[date(2027, 3, 29)], 'Lundi de Pâques')
        self.assertEqual(holidays_2027[date(2027, 5, 6)], 'Ascension')
        self.assertEqual(holidays_2027[date(2027, 5, 17)], 'Lundi de Pentecôte')
        self.assertNotIn(date(2027, 5, 17), dict(french_public_holidays(2027, whit_monday_worked=True)))
        for name in ('Congés', 'Conges', 'Ferié', 'Jour férié', 'Time Off', 'RTT', 'Maladie', 'Vacances'):
            self.assertTrue(is_absence_name(name), name)
        for name in ('Congrès', 'Congestion réseau', 'Lifetime offer', 'Intervention RTTE', 'Développement', 'Formation'):
            self.assertFalse(is_absence_name(name), name)
        # absence flag: set from the name at creation, then kept
        self.assertTrue(self.task_leave.timesheet_absence)
        self.assertTrue(self.task_rtt.timesheet_absence)
        self.assertFalse(self.task_work.timesheet_absence)
        absence_tasks = self.rules._get_absence_tasks()
        self.assertIn(self.task_leave, absence_tasks)
        self.assertNotIn(self.task_work, absence_tasks)
        self.task_leave.name = 'Audit'
        self.assertTrue(self.task_leave.timesheet_absence, 'renaming a task keeps its classification')
        self.task_review.timesheet_absence = True
        self.assertIn(self.task_review, self.rules._get_absence_tasks())
        # only timesheet administrators may change it; a basic user creating a task still gets the default
        from odoo.exceptions import AccessError
        project_user = self.env['res.users'].create({
            'name': 'Project User', 'login': 'consistency_project_user', 'email': 'consistency_project_user@example.com',
            'group_ids': [(6, 0, [self.env.ref('base.group_user').id, self.env.ref('project.group_project_user').id,
                                  self.env.ref(USER_GROUP).id])],
        })
        with self.assertRaises(AccessError):
            self.task_work.with_user(project_user).write({'timesheet_absence': True})
        with self.assertRaises(AccessError):
            self.env['project.task'].with_user(project_user).create({
                'name': 'Revue', 'project_id': self.project.id, 'timesheet_absence': True})
        by_user = self.env['project.task'].with_user(project_user).create({'name': 'Congés été', 'project_id': self.project.id})
        self.assertFalse(by_user.timesheet_absence, 'the name default only applies to tasks created by administrators')
        by_admin = self.env['project.task'].with_user(self.admin).create({'name': 'Congés hiver', 'project_id': self.project.id})
        self.assertTrue(by_admin.timesheet_absence)
        # anybody can still duplicate a task, and the copy keeps the flag
        copy = self.task_rtt.with_user(project_user).copy()
        self.assertTrue(copy.timesheet_absence)
        self.assertFalse(self.task_work.with_user(project_user).copy().timesheet_absence)
        # one day: the day of the encoding unit (what users enter), or the working schedule's day
        part_time = self.env['resource.calendar'].create({'name': 'Part time', 'hours_per_day': 4.0})
        self.other_employee.resource_calendar_id = part_time
        self.assertEqual(self.rules._get_hours_per_day(self.employee), 8.0)
        self.assertEqual(self.rules._get_hours_per_day(self.other_employee), 8.0,
                         'with timesheets encoded in days, one day is the unit day')
        self.company.timesheet_encode_uom_id = self.env.ref('uom.product_uom_hour')
        self.assertEqual(self.rules._get_hours_per_day(self.other_employee), 4.0)

    def test_one_day_per_calendar_day(self):
        self._log(date(2027, 3, 2), 4)
        line = self._log(date(2027, 3, 2), 4)
        with self.assertRefused('No more than one day'):
            self._log(date(2027, 3, 2), 1)
        with self.assertRaises(ValidationError):
            line.with_user(self.user).unit_amount = 5
        with self.assertRaises(ValidationError):
            line.with_user(self.user).write({'date': date(2027, 3, 3), 'unit_amount': 9})
        line.with_user(self.user).date = date(2027, 3, 3)
        self._log(date(2027, 3, 2), 4)
        # absences count too
        self._log(date(2027, 3, 4), 4, task=self.task_leave)
        self._log(date(2027, 3, 4), 4)
        with self.assertRaises(ValidationError):
            self._log(date(2027, 3, 5), 8.5, task=self.task_leave)
        # negative amounts do not make room
        self._log(date(2027, 3, 9), -8, task=self.task_leave)
        with self.assertRaises(ValidationError):
            self._log(date(2027, 3, 9), 16)
        # the limit applies to timesheet administrators too, and per employee
        with self.assertRaises(ValidationError):
            self._log(date(2027, 3, 4), 1, user=self.admin)
        self._log(date(2027, 3, 4), 8, user=self.admin, employee=self.other_employee)
        # several lines created at once
        with self.assertRaises(ValidationError):
            self.env['account.analytic.line'].with_user(self.user).create([{
                'name': '/', 'date': date(2027, 3, 8), 'unit_amount': hours, 'project_id': self.project.id,
                'task_id': self.task_work.id, 'employee_id': self.employee.id,
            } for hours in (6, 3)])

    def test_legacy_days_can_be_corrected(self):
        """Days that were inconsistent before the installation can be
        corrected step by step; only what makes them worse is refused."""
        first = self._log(date(2027, 3, 10), 8)
        second = self._log(date(2027, 3, 11), 8)
        self._legacy(second, date=date(2027, 3, 10))
        self.assertEqual(self._state(self.employee, date(2027, 3, 10))['total'], 16)
        first.with_user(self.user).task_id = self.task_review  # total unchanged
        first.with_user(self.user).unit_amount = 4
        with self.assertRaises(ValidationError):
            first.with_user(self.user).unit_amount = 6
        # moving a task to another project re-computes its lines, which is not checked
        self.task_review.project_id = self.other_project
        self.assertEqual(first.project_id, self.other_project)
        # legacy activity on a public holiday
        holiday_line = self._log(date(2027, 7, 13), 8)
        self._legacy(holiday_line, date=date(2027, 7, 14))
        holiday_line.with_user(self.user).write({'name': 'Correction', 'task_id': self.task_review.id})
        holiday_line.with_user(self.user).unit_amount = 4
        with self.assertRefused('public holiday'):
            holiday_line.with_user(self.user).unit_amount = 6
        holiday_line.with_user(self.user).task_id = self.task_leave

    def test_no_activity_on_public_holidays(self):
        with self.assertRefused('public holiday'):
            self._log(date(2027, 7, 14), 8)
        with self.assertRaises(ValidationError):
            self._log(date(2027, 3, 29), 4)  # Easter Monday
        line = self._log(date(2027, 7, 13), 8)
        with self.assertRaises(ValidationError):
            line.with_user(self.user).date = date(2027, 7, 14)
        # absences, empty lines and weekends are allowed
        self._log(date(2027, 7, 14), 8, task=self.task_leave)
        self._log(date(2027, 11, 11), 8, task=self.task_rtt)
        self._log(date(2027, 11, 1), 0)
        self._log(date(2027, 7, 17), 4)
        # changing an absence on a public holiday into an activity is refused
        absence = self._log(date(2027, 5, 6), 8, task=self.task_leave)
        with self.assertRaises(ValidationError):
            absence.with_user(self.user).task_id = self.task_work
        # timesheet administrators: exceptional work for others, not for themselves
        with self.assertRaises(ValidationError):
            self._log(date(2027, 1, 1), 8, user=self.admin, employee=self.admin_employee)
        self._log(date(2027, 1, 1), 8, user=self.admin, employee=self.other_employee)

    def test_analytic_line_becoming_a_timesheet(self):
        self._log(date(2027, 3, 15), 8)
        line = self.env['account.analytic.line'].create({
            'name': 'Analytic', 'date': date(2027, 3, 15), 'unit_amount': 8,
            'account_id': self.project.account_id.id, 'employee_id': self.employee.id})
        self.assertFalse(line.project_id)
        with self.assertRefused('No more than one day'):
            line.write({'task_id': self.task_work.id})

    def test_whit_monday(self):
        whit_monday = date(2027, 5, 17)
        self.assertNotIn(whit_monday, self.rules._get_public_holidays(2027, self.employee),
                         'Whit Monday is a worked day by default (journée de solidarité)')
        self._log(whit_monday, 4)
        self.env['ir.config_parameter'].sudo().set_param(WHIT_MONDAY_PARAM, 'False')
        self.assertEqual(self.rules._get_public_holidays(2027, self.employee)[whit_monday],
                         ('Lundi de Pentecôte', 'France'))
        with self.assertRefused('public holiday'):
            self._log(whit_monday, 4)

    def test_public_holidays_recorded_in_odoo(self):
        calendar = self.env['resource.calendar'].create({
            'name': 'Closures', 'tz': 'Europe/Paris', 'company_id': self.company.id})
        Leave = self.env['resource.calendar.leaves']

        def leave(name, date_from, date_to):
            record = Leave.create({'name': name, 'calendar_id': calendar.id, 'company_id': self.company.id,
                                   'date_from': datetime(2027, 1, 4, 8), 'date_to': datetime(2027, 1, 4, 9)})
            self.env.cr.execute('UPDATE resource_calendar_leaves SET date_from = %s, date_to = %s WHERE id = %s',
                                (date_from, date_to, record.id))
            self.env.invalidate_all()
            return record
        # dates are stored in UTC; Paris is UTC+1 in winter, UTC+2 in summer
        full_day = leave('Fermeture', datetime(2027, 12, 23, 23, 0), datetime(2027, 12, 24, 22, 59, 59))
        half_day = leave('Après-midi', datetime(2027, 12, 31, 12, 0), datetime(2027, 12, 31, 16, 0))
        utc_day = leave('Saisi en UTC', datetime(2027, 6, 10, 0, 0), datetime(2027, 6, 10, 23, 59, 59))
        to_midnight = leave('Jusqu à minuit', datetime(2027, 6, 15, 22, 0), datetime(2027, 6, 16, 22, 0))
        self.assertEqual(self.rules._get_leave_days(full_day, calendar), [date(2027, 12, 24)])
        self.assertEqual(self.rules._get_leave_days(half_day, calendar), [], 'a half day closure is not a public holiday')
        self.assertEqual(self.rules._get_leave_days(utc_day, calendar), [date(2027, 6, 10)])
        self.assertEqual(self.rules._get_leave_days(to_midnight, calendar), [date(2027, 6, 16)], 'the end is exclusive')
        holidays = self.rules._get_public_holidays(2027)
        self.assertEqual(holidays[date(2027, 12, 24)], ('Fermeture', 'Odoo'))
        self.assertNotIn(date(2027, 12, 31), holidays)
        self.assertNotIn(date(2027, 12, 24), self.rules._get_public_holidays(2027, self.employee),
                         'a public holiday of another working schedule does not apply')

    def test_generated_time_off_is_never_refused(self):
        """Odoo generates timesheets for time off and public holidays: they
        are never refused, and an absence logged by hand for the same day is
        not counted twice."""
        Line = self.env['account.analytic.line']
        if 'global_leave_id' not in Line._fields or not self.company.leave_timesheet_task_id:
            self.skipTest('project_timesheet_holidays is not configured')
        self._log(date(2027, 9, 6), 8, task=self.task_leave)
        activity = self._log(date(2027, 9, 7), 8)
        self.env.user.tz = 'Europe/Paris'
        public_holiday = self.env['resource.calendar.leaves'].create({
            'name': 'Fermeture', 'calendar_id': self.calendar.id, 'company_id': self.company.id,
            'date_from': datetime(2027, 9, 5, 22, 0), 'date_to': datetime(2027, 9, 7, 21, 59, 59),
        })
        generated = Line.search([('global_leave_id', '=', public_holiday.id), ('employee_id', '=', self.employee.id)])
        self.assertEqual(sorted(generated.mapped('date')), [date(2027, 9, 6), date(2027, 9, 7)])
        self.assertEqual(self._state(self.employee, date(2027, 9, 6))['total'], 8, 'same absence logged twice')
        self.assertEqual(self._state(self.employee, date(2027, 9, 7))['total'], 16)
        with self.assertRaises(ValidationError):
            self._log(date(2027, 9, 6), 1)
        activity.with_user(self.user).unit_amount = 4
        # users may reduce the lines generated for them, not enlarge them
        generated_line = generated.filtered(lambda line: line.date == date(2027, 9, 6))
        with self.assertRefused('No more than one day'):
            generated_line.with_user(self.user).unit_amount = 16
        generated_line.with_user(self.user).unit_amount = 4
        public_holiday.unlink()
