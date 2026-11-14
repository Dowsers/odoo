# -*- coding: utf-8 -*-
import json
from datetime import date, datetime
from unittest.mock import patch

import requests

from odoo import fields
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests import TransactionCase, tagged

from odoo.addons.hr_timesheet_consistency.models.timesheet_day_rules import WHIT_MONDAY_PARAM

from ..models import hr_public_holiday_fr
from ..models.hr_public_holiday_fr import API_SOURCE, CRON_XMLID

REQUESTS_GET = 'odoo.addons.hr_holidays_public_fr.models.hr_public_holiday_fr.requests.get'
# Answer of https://calendrier.api.gouv.fr/jours-feries/metropole.json for 2030 and 2031
OFFICIAL = {
    '2030-01-01': '1er janvier', '2030-04-22': 'Lundi de Pâques', '2030-05-01': '1er mai',
    '2030-05-08': '8 mai', '2030-05-30': 'Ascension', '2030-06-10': 'Lundi de Pentecôte',
    '2030-07-14': '14 juillet', '2030-08-15': 'Assomption', '2030-11-01': 'Toussaint',
    '2030-11-11': '11 novembre', '2030-12-25': 'Jour de Noël',
    '2031-01-01': '1er janvier', '2031-04-14': 'Lundi de Pâques', '2031-05-01': '1er mai',
    '2031-05-08': '8 mai', '2031-05-22': 'Ascension', '2031-06-02': 'Lundi de Pentecôte',
    '2031-07-14': '14 juillet', '2031-08-15': 'Assomption', '2031-11-01': 'Toussaint',
    '2031-11-11': '11 novembre', '2031-12-25': 'Jour de Noël',
}
# Day of the imports: a Wednesday; the public holidays before it are past
TODAY = date(2030, 6, 12)
WHIT_MONDAY_2030, WHIT_MONDAY_2031 = date(2030, 6, 10), date(2031, 6, 2)


def without(*days):
    return {day: label for day, label in OFFICIAL.items() if day not in days}


class FakeResponse:
    """Answer of requests.get(..., stream=True), used as a context manager."""

    def __init__(self, payload, status=200):
        self.payload = payload
        self.status_code = status

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError('%s Client Error' % self.status_code)

    def iter_content(self, chunk_size=None):
        body = self.payload if isinstance(self.payload, bytes) else json.dumps(self.payload).encode()
        for start in range(0, len(body), chunk_size or len(body) or 1):
            yield body[start:start + (chunk_size or len(body))]


@tagged('post_install', '-at_install')
class TestFrenchPublicHolidays(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env = cls.env(context=dict(cls.env.context, tracking_disable=True, no_reset_password=True))
        cls.company = cls.env['res.company'].create({
            'name': 'Société Test Jours Fériés', 'country_id': cls.env.ref('base.fr').id})
        cls.calendar = cls.env['resource.calendar'].create({
            'name': 'Test 40h', 'tz': 'Europe/Paris', 'hours_per_day': 8.0, 'company_id': cls.company.id})
        cls.company.resource_calendar_id = cls.calendar
        cls.employee = cls.env['hr.employee'].create({
            'name': 'Employé Test', 'company_id': cls.company.id, 'resource_calendar_id': cls.calendar.id})
        cls.admin = cls.env.ref('base.user_admin')
        cls.Official = cls.env['hr.public.holiday.fr']
        cls.Leave = cls.env['resource.calendar.leaves']
        cls.rules = cls.env['hr.timesheet.day.rules']
        cls.Param = cls.env['ir.config_parameter'].sudo()
        cls.Param.set_param(WHIT_MONDAY_PARAM, 'True')

    def _import(self, payload=None, today=TODAY):
        payload = OFFICIAL if payload is None else payload
        with patch(REQUESTS_GET, return_value=FakeResponse(payload)):
            return self.Official._import_public_holidays(self.company, raise_errors=True, today=today)[self.company]

    def _row(self, day):
        return self.Official.search([('company_id', '=', self.company.id), ('date', '=', day)])

    def _leaves(self):
        return self.Leave.search([('company_id', '=', self.company.id), ('resource_id', '=', False)])

    def _timesheets(self, leaves):
        return self.env['account.analytic.line'].search([
            ('global_leave_id', 'in', leaves.ids), ('employee_id', '=', self.employee.id)])

    def _holidays(self, year):
        return self.rules._get_public_holidays(year, self.employee)

    def _time_off(self, date_from, date_to):
        leave_type = self.env['hr.leave.type'].create({
            'name': 'Congés test', 'requires_allocation': False, 'company_id': self.company.id})
        return self.env['hr.leave'].with_company(self.company).create({
            'name': 'Vacances', 'employee_id': self.employee.id, 'holiday_status_id': leave_type.id,
            'request_date_from': date_from, 'request_date_to': date_to})

    def test_api_answers(self):
        with patch(REQUESTS_GET, return_value=FakeResponse({'2030-01-01': ' 1er  janvier '})) as get:
            self.assertEqual(self.Official._fetch_official_holidays('alsace-moselle'), {date(2030, 1, 1): '1er janvier'})
        self.assertEqual(get.call_args.args[0], 'https://calendrier.api.gouv.fr/jours-feries/alsace-moselle.json')
        self.assertTrue(get.call_args.kwargs.get('timeout'))
        bad_answers = [
            FakeResponse(b'<html>Page not found</html>', status=404),
            FakeResponse(b'<html>not JSON</html>'),
            FakeResponse(b'\xff\xfe not UTF-8'),
            FakeResponse([]),
            FakeResponse({}),
            FakeResponse({'2030-13-01': 'Mauvaise date'}),
            FakeResponse({'2030-01-01': '  '}),
            FakeResponse({'2030-01-01': None}),
            FakeResponse(b'{"2030-01-01": "' + b'x' * (hr_public_holiday_fr.API_MAX_BYTES + 1) + b'"}'),
        ]
        for answer in bad_answers:
            with self.subTest(answer=str(answer.payload)[:40]), patch(REQUESTS_GET, return_value=answer), \
                    self.assertRaises(UserError):
                self.Official._fetch_official_holidays('metropole')
        with patch(REQUESTS_GET, side_effect=requests.ConnectionError('unreachable')), self.assertRaises(UserError):
            self.Official._fetch_official_holidays('metropole')
        with patch(REQUESTS_GET) as get, self.assertRaises(UserError):
            self.Official._fetch_official_holidays('../metropole')
        get.assert_not_called()

    def test_import(self):
        self.assertEqual(self.company.fr_public_holidays_zone, 'metropole')
        self.assertEqual(self._import(), {'created': 20, 'removed': 0}, '22 days, Whit Mondays worked')
        leaves = self._leaves()
        self.assertEqual(len(leaves), 20)
        self.assertFalse(leaves.calendar_id, 'public holidays of every working schedule of the company')
        # whole days in the time zone of the working schedule, stored in UTC
        christmas = leaves.filtered(lambda leave: leave.date_from == datetime(2030, 12, 24, 23, 0))
        self.assertEqual((christmas.name, christmas.date_to), ('Jour de Noël', datetime(2030, 12, 25, 22, 59, 59)))
        july = leaves.filtered(lambda leave: leave.date_from == datetime(2030, 7, 13, 22, 0))
        self.assertEqual((july.name, july.date_to), ('14 juillet', datetime(2030, 7, 14, 21, 59, 59)))
        self.assertEqual(self._row(WHIT_MONDAY_2030).state, 'worked')
        self.assertFalse(self._row(WHIT_MONDAY_2030).leave_id)
        self.assertEqual(self._row(date(2030, 7, 14)).leave_id, july)
        # timesheets generated from today only: 4 working days in 2030, 9 in 2031
        lines = self._timesheets(leaves)
        self.assertFalse(lines.filtered(lambda line: line.date < TODAY), 'no timesheet for the past public holidays')
        self.assertEqual(len(lines), 13)
        self.assertEqual(min(lines.mapped('date')), date(2030, 8, 15))
        self.assertEqual(set(lines.mapped('unit_amount')), {8.0})
        self.assertTrue(self.company.fr_public_holidays_sync_date)
        # a second import changes nothing
        self.assertEqual(self._import(), {'created': 0, 'removed': 0})
        self.assertEqual(self._leaves(), leaves)
        self.assertEqual(self._timesheets(leaves), lines)

    def test_abnormal_years_change_nothing(self):
        self._import()
        leaves = self._leaves()
        abnormal = [
            {day: label for day, label in OFFICIAL.items() if day.startswith('2030')},  # next year missing
            without(*[day for day in OFFICIAL if day.startswith('2030-0')]),  # 3 days left in 2030
            dict(OFFICIAL, **{'2031-02-%02d' % day: 'Férié' for day in range(1, 12)}),  # 22 days in 2031
        ]
        for payload in abnormal:
            with self.subTest(days=len(payload)), self.assertRaises(UserError):
                self._import(payload)
            self.assertEqual(self._leaves(), leaves)

    def test_timesheet_rules_use_the_public_holidays_of_odoo(self):
        self.assertEqual(self._holidays(2030)[date(2030, 5, 8)], ('Victoire 1945', 'France'),
                         'computed French public holidays before the import')
        self._import()
        holidays = self._holidays(2030)
        self.assertEqual(len(holidays), 10)
        self.assertEqual(holidays[date(2030, 5, 8)], ('8 mai', API_SOURCE))
        self.assertNotIn(WHIT_MONDAY_2030, holidays)
        self.assertEqual(self._holidays(2032)[date(2032, 5, 8)], ('Victoire 1945', 'France'),
                         'years not imported: computed French public holidays')
        # hr_timesheet_consistency: no activity on an imported public holiday
        user = self.env['res.users'].create({
            'name': 'Utilisateur Test Fériés', 'login': 'fr_public_holidays_user',
            'company_id': self.company.id, 'company_ids': [(6, 0, self.company.ids)],
            'group_ids': [(6, 0, [self.env.ref('base.group_user').id,
                                  self.env.ref('hr_timesheet.group_hr_timesheet_user').id])],
        })
        self.employee.user_id = user
        plan = self.env['account.analytic.plan'].create({'name': 'Plan test fériés'})
        project = self.env['project.project'].create({
            'name': 'Recherche', 'allow_timesheets': True, 'privacy_visibility': 'employees',
            'company_id': self.company.id,
            'account_id': self.env['account.analytic.account'].create({
                'name': 'Recherche', 'plan_id': plan.id, 'company_id': self.company.id}).id,
        })
        task = self.env['project.task'].create({'name': 'Développement', 'project_id': project.id})
        Line = self.env['account.analytic.line'].with_user(user).with_company(self.company)
        values = {'name': '/', 'unit_amount': 8, 'project_id': project.id, 'task_id': task.id,
                  'employee_id': self.employee.id}
        with self.assertRaises(ValidationError):
            Line.create(dict(values, date=date(2030, 4, 22)))
        Line.create(dict(values, date=date(2030, 4, 23)))

    def test_deleted_public_holiday_is_never_imported_again(self):
        self._import()
        assumption = self._row(date(2030, 8, 15))
        lines = self._timesheets(assumption.leave_id)
        self.assertTrue(lines)
        assumption.leave_id.unlink()
        self.assertEqual(assumption.state, 'deleted')
        self.assertFalse(lines.exists())
        self.assertEqual(self._import(), {'created': 0, 'removed': 0})
        self.assertEqual(assumption.state, 'deleted')
        self.assertNotIn(date(2030, 8, 15), self._holidays(2030), 'the rules follow the public holidays of Odoo')
        # not even after the government stopped publishing it for a while
        self.assertEqual(self._import(without('2030-08-15')), {'created': 0, 'removed': 0})
        self.assertEqual(assumption.state, 'deleted')
        self.assertEqual(self._import(), {'created': 0, 'removed': 0})
        self.assertEqual(assumption.state, 'deleted')
        self.assertFalse(assumption.leave_id)

    def test_whit_monday_setting_applies_to_upcoming_days(self):
        self._import()
        past, upcoming = self._row(WHIT_MONDAY_2030), self._row(WHIT_MONDAY_2031)
        self.assertEqual((past.state, upcoming.state), ('worked', 'worked'))
        # Whit Monday becomes a public holiday: only the upcoming one is created
        self.Param.set_param(WHIT_MONDAY_PARAM, 'False')
        self.assertEqual(self._import(), {'created': 1, 'removed': 0})
        self.assertEqual((past.state, upcoming.state), ('worked', 'imported'))
        self.assertNotIn(WHIT_MONDAY_2030, self._holidays(2030), 'the past is not rewritten')
        self.assertEqual(self._holidays(2031)[WHIT_MONDAY_2031], ('Lundi de Pentecôte', API_SOURCE))
        self.assertTrue(self._timesheets(upcoming.leave_id))
        # it is a worked day again: the upcoming one is removed
        self.Param.set_param(WHIT_MONDAY_PARAM, 'True')
        self.assertEqual(self._import(), {'created': 0, 'removed': 1})
        self.assertEqual((past.state, upcoming.state), ('worked', 'worked'))
        self.assertFalse(upcoming.leave_id)
        self.assertNotIn(WHIT_MONDAY_2031, self._holidays(2031))

    def test_past_whit_monday_is_kept(self):
        """A Whit Monday that was a public holiday stays one, with its
        timesheets, when Whit Monday becomes a worked day afterwards."""
        self.Param.set_param(WHIT_MONDAY_PARAM, 'False')
        self.assertEqual(self._import(today=date(2030, 1, 10)), {'created': 22, 'removed': 0})
        past, upcoming = self._row(WHIT_MONDAY_2030), self._row(WHIT_MONDAY_2031)
        lines = self._timesheets(past.leave_id)
        self.assertEqual(lines.mapped('date'), [WHIT_MONDAY_2030])
        time_off = self._time_off(date(2030, 6, 10), date(2030, 6, 14))
        self.assertEqual(time_off.number_of_days, 4)
        self.Param.set_param(WHIT_MONDAY_PARAM, 'True')
        self.assertEqual(self._import(today=date(2030, 9, 2)), {'created': 0, 'removed': 1})
        self.assertEqual((past.state, upcoming.state), ('imported', 'worked'))
        self.assertTrue(past.leave_id.exists())
        self.assertTrue(lines.exists(), 'the timesheets of the past public holiday are kept')
        self.assertEqual(time_off.number_of_days, 4)
        self.assertIn(WHIT_MONDAY_2030, self._holidays(2030))

    def test_first_import_when_whit_monday_is_a_public_holiday(self):
        self.Param.set_param(WHIT_MONDAY_PARAM, 'False')
        self.assertEqual(self._import(), {'created': 22, 'removed': 0})
        past = self._row(WHIT_MONDAY_2030)
        self.assertEqual(past.state, 'imported')
        self.assertFalse(self._timesheets(past.leave_id), 'past day: no timesheet generated')
        self.assertIn(WHIT_MONDAY_2030, self._holidays(2030))

    def test_public_holidays_recorded_by_hand(self):
        self.env.user.tz = 'Europe/Paris'
        Leave = self.Leave.with_company(self.company)
        new_year = Leave.create({
            'name': 'Nouvel an', 'company_id': self.company.id,
            'date_from': datetime(2031, 1, 1, 0, 0), 'date_to': datetime(2031, 1, 1, 23, 59, 59)})
        closure = Leave.create({
            'name': 'Fermeture', 'company_id': self.company.id, 'calendar_id': self.calendar.id,
            'date_from': datetime(2031, 5, 8, 0, 0), 'date_to': datetime(2031, 5, 9, 23, 59, 59)})
        self.assertEqual(self._import()['created'], 18)
        row = self._row(date(2031, 1, 1))
        self.assertEqual((row.state, row.leave_id), ('existing', new_year))
        self.assertEqual((self._row(date(2031, 5, 8)).state, self._row(date(2031, 5, 8)).leave_id),
                         ('existing', closure))
        holidays = self._holidays(2031)
        self.assertEqual(holidays[date(2031, 1, 1)], ('Nouvel an', 'Odoo'))
        self.assertEqual(holidays[date(2031, 5, 9)], ('Fermeture', 'Odoo'))
        # no longer official, then official again: it is never taken over nor removed
        self.assertEqual(self._import(without('2031-01-01')), {'created': 0, 'removed': 0})
        self.assertEqual((row.state, row.leave_id), ('withdrawn', self.Leave))
        self.assertEqual(self._import(), {'created': 0, 'removed': 0})
        self.assertEqual((row.state, row.leave_id), ('existing', new_year))
        self.assertEqual(self._import(without('2031-01-01')), {'created': 0, 'removed': 0})
        self.assertTrue(new_year.exists())
        self.assertEqual(new_year.name, 'Nouvel an')
        self._import()
        # deleted by hand: the official public holiday takes its place at the next import
        new_year.unlink()
        self.assertEqual(row.state, 'existing')
        self.assertNotIn(date(2031, 1, 1), self._holidays(2031), 'the rules follow the public holidays of Odoo')
        self.assertEqual(self._import(), {'created': 1, 'removed': 0})
        self.assertEqual((row.state, row.leave_id.name), ('imported', '1er janvier'))
        self.assertEqual(self._holidays(2031)[date(2031, 1, 1)], ('1er janvier', API_SOURCE))

    def test_no_longer_official(self):
        self._import()
        christmas, victory = self._row(date(2030, 12, 25)), self._row(date(2030, 5, 8))
        christmas_leave, victory_leave = christmas.leave_id, victory.leave_id
        # a pending request over Christmas gets no timesheet when the public holiday is removed
        time_off = self._time_off(date(2030, 12, 23), date(2030, 12, 27))
        self.assertEqual((time_off.state, time_off.number_of_days), ('confirm', 4))
        self.assertEqual(self._import(without('2030-12-25', '2030-05-08')), {'created': 0, 'removed': 1})
        self.assertFalse(christmas_leave.exists(), 'an upcoming public holiday no longer official is removed')
        self.assertEqual(christmas.state, 'withdrawn')
        self.assertTrue(victory_leave.exists(), 'a past public holiday is kept')
        self.assertEqual(victory.state, 'withdrawn')
        self.assertNotIn(date(2030, 12, 25), self._holidays(2030))
        self.assertIn(date(2030, 5, 8), self._holidays(2030))
        self.assertEqual(time_off.number_of_days, 5)
        self.assertFalse(self.env['account.analytic.line'].search([('holiday_id', '=', time_off.id)]),
                         'timesheets are only generated for validated time off')
        # official again
        self.assertEqual(self._import(), {'created': 1, 'removed': 0})
        self.assertEqual((christmas.state, victory.state), ('imported', 'imported'))
        self.assertEqual(victory.leave_id, victory_leave)
        self.assertEqual(time_off.number_of_days, 4)

    def test_pending_time_off_shortened(self):
        time_off = self._time_off(date(2031, 5, 5), date(2031, 5, 9))
        self.assertEqual(time_off.number_of_days, 5)
        self._import()
        self.assertEqual(time_off.number_of_days, 4, '8 May is no longer counted')

    def test_errors_and_rights(self):
        with patch(REQUESTS_GET, side_effect=requests.ConnectionError('API unreachable')):
            self.assertEqual(self.Official._import_public_holidays(self.company, today=TODAY), {})
            self.Official._cron_import()  # never fails
        self.assertIn('API unreachable', self.company.fr_public_holidays_sync_error)
        self.assertFalse(self.company.fr_public_holidays_sync_date)
        self.assertFalse(self._leaves())
        with patch(REQUESTS_GET, side_effect=requests.Timeout('timeout')), self.assertRaises(UserError):
            self.Official.with_user(self.admin)._action_import(self.company)
        officer = self.env['res.users'].create({
            'name': 'Responsable congés', 'login': 'fr_public_holidays_officer',
            'group_ids': [(6, 0, [self.env.ref('base.group_user').id,
                                  self.env.ref('hr_holidays.group_hr_holidays_user').id])],
        })
        with patch(REQUESTS_GET) as get:
            with self.assertRaises(AccessError):
                self.Official.with_user(officer).action_import()
            with self.assertRaises(AccessError):
                self.Leave.with_user(officer).action_import_fr_public_holidays()
        get.assert_not_called()
        # the buttons import the current and the next year
        year = fields.Date.today().year
        payload = {
            '%s-%s' % (holiday_year, day[5:]): label
            for holiday_year in (year, year + 1)
            for day, label in OFFICIAL.items() if day.startswith('2030') and label != 'Lundi de Pentecôte'
        }
        with patch(REQUESTS_GET, return_value=FakeResponse(payload)):
            action = self.Official.with_user(self.admin)._action_import(self.company)
        self.assertEqual(action['tag'], 'display_notification')
        self.assertFalse(self.company.fr_public_holidays_sync_error)
        self.assertTrue(self.company.fr_public_holidays_sync_date)
        self.assertEqual(len(self._leaves()), 20)

    def test_settings(self):
        self.company.country_id = self.env.ref('base.gp')
        self.assertEqual(self.company.fr_public_holidays_zone, 'guadeloupe')
        self.company.country_id = self.env.ref('base.be')
        self.assertFalse(self.company.fr_public_holidays_zone)
        self.company.country_id = self.env.ref('base.fr')
        self.assertEqual(self.company.fr_public_holidays_zone, 'metropole')
        cron = self.env.ref(CRON_XMLID)
        cron.active = True  # scheduled actions are deactivated in a neutralized database
        Trigger = self.env['ir.cron.trigger']

        def triggers():
            return Trigger.search_count([('cron_id', '=', cron.id)])
        Settings = self.env['res.config.settings'].with_company(self.company)
        settings = Settings.create({})
        self.assertTrue(settings.fr_whit_monday_worked)
        self.assertEqual(settings.fr_public_holidays_zone, 'metropole')
        before = triggers()
        settings.fr_public_holidays_zone = 'alsace-moselle'
        self.assertEqual(self.company.fr_public_holidays_zone, 'alsace-moselle')
        self.assertEqual(triggers(), before + 1, 'a new zone triggers the import')
        settings.fr_whit_monday_worked = False
        settings.execute()
        self.assertEqual(self.Param.get_param(WHIT_MONDAY_PARAM), 'False')
        self.assertEqual(triggers(), before + 2, 'the Whit Monday choice triggers the import')
        Settings.create({'fr_whit_monday_worked': True}).execute()
        self.assertTrue(self.rules._whit_monday_worked())
        self.assertEqual(self.Param.get_param(WHIT_MONDAY_PARAM), 'True')
