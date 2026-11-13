# -*- coding: utf-8 -*-
"""Rules about timesheet days shared by the consistency checks of this module
and by the CIR export (hr_timesheet_cir_export): length of a day, public
holidays and absences."""
import re
import unicodedata
from datetime import date, datetime, time, timedelta

import pytz

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError
from odoo.tools import float_compare
from odoo.tools.misc import format_date, formatLang

ADMIN_GROUP = 'hr_timesheet.group_timesheet_manager'
# ir.config_parameter: "True" when Whit Monday is a worked day (journée de
# solidarité), "False" when it is a public holiday.
WHIT_MONDAY_PARAM = 'hr_timesheet_consistency.whit_monday_worked'
# Words that, in a task name, make the task an absence task by default
# (accents and case ignored, whole words only).
ABSENCE_NAME_RE = re.compile(
    r'(?<![a-z0-9])(conges?|feries?|time ?off|absences?|rtt|maladie|vacances)(?![a-z0-9])')


def easter_date(year):
    """Gregorian Easter Sunday (Meeus / Jones / Butcher algorithm)."""
    a = year % 19
    b, c = divmod(year, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month, day = divmod(h + l - 7 * m + 114, 31)
    return date(year, month, day + 1)


def french_public_holidays(year, whit_monday_worked=False):
    """French public holidays of ``year`` as a list of (date, label).

    :param whit_monday_worked: leave Whit Monday out (journée de solidarité)
    """
    easter = easter_date(year)
    holidays = [
        (date(year, 1, 1), "Jour de l'an"),
        (easter + timedelta(days=1), 'Lundi de Pâques'),
        (date(year, 5, 1), 'Fête du Travail'),
        (date(year, 5, 8), 'Victoire 1945'),
        (easter + timedelta(days=39), 'Ascension'),
        (easter + timedelta(days=50), 'Lundi de Pentecôte'),
        (date(year, 7, 14), 'Fête Nationale'),
        (date(year, 8, 15), 'Assomption'),
        (date(year, 11, 1), 'Toussaint'),
        (date(year, 11, 11), 'Armistice 1918'),
        (date(year, 12, 25), 'Noël'),
    ]
    if whit_monday_worked:
        holidays = [(day, label) for day, label in holidays if label != 'Lundi de Pentecôte']
    return holidays


def is_absence_name(name):
    """Whether a task name designates an absence (congé, férié, RTT...)."""
    text = unicodedata.normalize('NFKD', name or '')
    text = ''.join(char for char in text if not unicodedata.combining(char)).lower()
    return bool(ABSENCE_NAME_RE.search(text))


class TimesheetDayRules(models.AbstractModel):
    _name = 'hr.timesheet.day.rules'
    _description = 'Timesheet day rules'

    # ------------------------------------------------------------------
    # Shared rules
    # ------------------------------------------------------------------
    @api.model
    def _get_hours_per_day(self, employee):
        """Hours of one day for ``employee``: the day of the timesheet
        encoding unit when the company encodes timesheets in days (what users
        enter), otherwise the hours per day of the working schedule."""
        employee = employee.sudo()
        company = employee.company_id or self.env.company
        hour_uom = self.env.ref('uom.product_uom_hour', raise_if_not_found=False)
        encode_uom = company.timesheet_encode_uom_id
        if hour_uom and encode_uom and encode_uom != hour_uom:
            day = encode_uom._compute_quantity(1.0, hour_uom, round=False, raise_if_failure=False)
            if float_compare(day, 1.0, precision_digits=4) > 0:
                return day
        calendar = employee.resource_calendar_id or company.resource_calendar_id
        return calendar.hours_per_day or 8.0

    @api.model
    def _get_day_limit(self, employee):
        """Most hours that can be logged on one day: one day (see
        _get_hours_per_day), or the schedule's day when it is longer."""
        employee = employee.sudo()
        calendar = employee.resource_calendar_id or employee.company_id.resource_calendar_id
        return max(self._get_hours_per_day(employee), calendar.hours_per_day or 0.0)

    @api.model
    def _get_absence_tasks(self):
        """Tasks whose timesheets record an absence: the tasks flagged as
        absences and the time off task of the companies."""
        Task = self.env['project.task'].sudo().with_context(active_test=False)
        tasks = Task.search([('timesheet_absence', '=', True)])
        companies = self.env['res.company'].sudo().search([])
        if 'leave_timesheet_task_id' in companies._fields:
            tasks |= companies.leave_timesheet_task_id
        return tasks.exists().with_env(self.env)

    @api.model
    def _is_absence(self, task_id, absence_task_ids):
        """Whether a timesheet on ``task_id`` records an absence."""
        return bool(task_id and task_id in absence_task_ids)

    @api.model
    def _whit_monday_worked(self):
        value = self.env['ir.config_parameter'].sudo().get_param(WHIT_MONDAY_PARAM, 'True')
        return str(value).strip().lower() not in ('false', '0', 'no', 'non', '')

    @api.model
    def _get_public_holidays(self, year, employee=None):
        """Public holidays of ``year`` as ``{date: (label, source)}``, sorted.

        The French public holidays (source ``'France'``; Whit Monday only when
        it is not a worked day, see ``WHIT_MONDAY_PARAM``) are completed, and
        relabelled, by the public holidays recorded in Odoo (global time off of
        the working schedules, source ``'Odoo'``) that apply to ``employee``
        (company and working schedule) or, without employee, to the current
        companies. A public holiday recorded in Odoo counts on the days whose
        working hours it fully covers.
        """
        holidays = {
            day: (label, 'France')
            for day, label in french_public_holidays(year, self._whit_monday_worked())
        }
        domain = [
            ('resource_id', '=', False),
            ('date_from', '<=', datetime(year, 12, 31, 23, 59, 59) + timedelta(days=1)),
            ('date_to', '>=', datetime(year, 1, 1) - timedelta(days=1)),
        ]
        employee = employee.sudo() if employee else None
        calendar = None
        if employee:
            calendar = employee.resource_calendar_id or employee.company_id.resource_calendar_id
            domain.append(('company_id', 'in', [False, employee.company_id.id]))
            domain.append(('calendar_id', 'in', [False] + calendar.ids))
        else:
            domain.append(('company_id', 'in', [False] + self.env.companies.ids))
        for leave in self.env['resource.calendar.leaves'].sudo().search(domain, order='date_from, id'):
            leave_calendar = leave.calendar_id or calendar or leave.company_id.resource_calendar_id
            for day in self._get_leave_days(leave, leave_calendar, employee):
                if day.year != year:
                    continue
                label = leave.name or holidays.get(day, (_('Public holiday'),))[0]
                holidays[day] = (label, 'Odoo')
        return dict(sorted(holidays.items()))

    @api.model
    def _get_leave_days(self, leave, calendar, employee=None):
        """Dates (in the working schedule time zone) whose working hours the
        global time off ``leave`` fully covers. A day without working hours
        counts when the time off covers the whole day."""
        tz = pytz.timezone(calendar.tz or (employee and employee.tz) or 'UTC')
        start = pytz.utc.localize(leave.date_from)
        stop = pytz.utc.localize(leave.date_to)
        if stop <= start:
            return []
        day = start.astimezone(tz).date()
        last = (stop - timedelta(microseconds=1)).astimezone(tz).date()
        days = []
        while day <= last:
            day_start = tz.localize(datetime.combine(day, time.min))
            day_end = tz.localize(datetime.combine(day + timedelta(days=1), time.min))
            work = calendar._attendance_intervals_batch(day_start, day_end)[False] if calendar else []
            work = list(work)
            if work:
                covered = all(start <= work_start and work_stop <= stop for work_start, work_stop, _meta in work)
            else:
                covered = start <= day_start and day_end - timedelta(seconds=1) <= stop
            if covered:
                days.append(day)
            day += timedelta(days=1)
        return days

    # ------------------------------------------------------------------
    # Consistency checks (called by account.analytic.line create / write)
    # ------------------------------------------------------------------
    @api.model
    def _is_generated_absence(self, line, absence_task_ids):
        """Absence generated by Odoo from a time off or a public holiday."""
        generated = ('holiday_id' in line._fields and line.holiday_id) or \
            ('global_leave_id' in line._fields and line.global_leave_id)
        return bool(generated) and self._is_absence(line.task_id.id, absence_task_ids)

    @api.model
    def _lock_employees(self, employee_ids):
        """Make concurrent timesheet operations on the same employee conflict.

        Odoo transactions are REPEATABLE READ: a second transaction would not
        see the lines of a first one committed after its snapshot. Updating
        the employee rows makes the second one wait, then fail with a
        serialization error, which Odoo retries with a fresh snapshot.
        """
        employee_ids = sorted(set(employee_ids))
        if employee_ids:
            self.env.cr.execute('UPDATE hr_employee SET id = id WHERE id IN %s', (tuple(employee_ids),))

    @api.model
    def _affected_days(self, lines, vals=None):
        """(employee_id, date) pairs touched by ``lines`` (timesheets), before
        and, for a write of ``vals``, after the write."""
        pairs = set()
        for line in lines.sudo():
            if line.employee_id and line.date:
                pairs.add((line.employee_id.id, line.date))
            if vals:
                employee_id = vals['employee_id'] if 'employee_id' in vals else line.employee_id.id
                day = fields.Date.to_date(vals['date']) if 'date' in vals else line.date
                if employee_id and day:
                    pairs.add((employee_id, day))
        return pairs

    @api.model
    def _day_states(self, pairs, absence_task_ids, exclude_ids=()):
        """Hours logged per (employee_id, date) of ``pairs``:
        ``{'activity', 'generated_absence', 'manual_absence', 'total'}``.

        Negative amounts count as 0. An absence logged by hand and the
        absence Odoo generates for the same time off or public holiday are
        the same absence: the day total counts the larger of the two.
        """
        states = {pair: {'activity': 0.0, 'generated_absence': 0.0, 'manual_absence': 0.0} for pair in pairs}
        if pairs:
            Line = self.env['account.analytic.line'].sudo()
            optional = [name for name in ('holiday_id', 'global_leave_id') if name in Line._fields]
            domain = [
                ('project_id', '!=', False),
                ('employee_id', 'in', list({employee_id for employee_id, _day in pairs})),
                ('date', 'in', list({day for _employee_id, day in pairs})),
            ]
            if exclude_ids:
                domain.append(('id', 'not in', list(exclude_ids)))
            for line in Line.search_read(domain, ['employee_id', 'date', 'unit_amount', 'task_id'] + optional):
                pair = (line['employee_id'][0], fields.Date.to_date(line['date']))
                if pair not in states:
                    continue
                amount = max(line['unit_amount'] or 0.0, 0.0)
                task_id = line['task_id'] and line['task_id'][0]
                if not self._is_absence(task_id, absence_task_ids):
                    states[pair]['activity'] += amount
                elif any(line.get(name) for name in optional):
                    states[pair]['generated_absence'] += amount
                else:
                    states[pair]['manual_absence'] += amount
        for state in states.values():
            state['total'] = state['activity'] + max(state['generated_absence'], state['manual_absence'])
        return states

    @api.model
    def _check_new_lines(self, lines):
        """Checks after the creation of timesheets ``lines``."""
        absence_task_ids = set(self._get_absence_tasks().ids)
        triggers = lines.sudo().filtered(
            lambda line: line.project_id and line.employee_id and line.date
            and not (self.env.su and self._is_generated_absence(line, absence_task_ids)))
        if not triggers:
            return
        pairs = self._affected_days(triggers)
        self._lock_employees(employee_id for employee_id, _day in pairs)
        before = self._day_states(pairs, absence_task_ids, exclude_ids=lines.ids)
        after = self._day_states(pairs, absence_task_ids)
        self._raise_if_worse(pairs, before, after)

    @api.model
    def _raise_if_worse(self, pairs, before, after):
        """Refuse the days that the operation made inconsistent, or more
        inconsistent: more than one day logged, or more activity on a public
        holiday. Lines that were already inconsistent can still be corrected.

        Timesheet administrators may log exceptional work on a public holiday
        for other employees, not for themselves.
        """
        Employee = self.env['hr.employee'].sudo()
        is_admin = self.env.user.has_group(ADMIN_GROUP)
        holidays_cache = {}
        over_day, on_holiday = [], []
        for employee_id, day in sorted(pairs, key=lambda pair: (pair[1], pair[0])):
            employee = Employee.browse(employee_id)
            old, new = before[(employee_id, day)], after[(employee_id, day)]
            day_hours = self._get_hours_per_day(employee)
            if float_compare(new['total'], self._get_day_limit(employee), precision_digits=2) > 0 \
                    and float_compare(new['total'], old['total'], precision_digits=2) > 0:
                message = _(
                    "%(employee)s, %(date)s: %(days)s days logged",
                    employee=employee.name,
                    date=format_date(self.env, day),
                    days=formatLang(self.env, new['total'] / day_hours, digits=2),
                )
                if new['generated_absence']:
                    message += _(" (time off or public holiday recorded in Odoo included)")
                over_day.append(message)
            if float_compare(new['activity'], old['activity'], precision_digits=2) > 0:
                if is_admin and employee.user_id != self.env.user:
                    continue
                key = (day.year, employee_id)
                if key not in holidays_cache:
                    holidays_cache[key] = self._get_public_holidays(day.year, employee)
                holiday = holidays_cache[key].get(day)
                if holiday:
                    on_holiday.append(_(
                        "%(employee)s, %(date)s (%(holiday)s)",
                        employee=employee.name,
                        date=format_date(self.env, day),
                        holiday=holiday[0],
                    ))
        messages = []
        if over_day:
            messages.append(_(
                "No more than one day can be logged on a calendar day:\n%s",
                "\n".join(over_day),
            ))
        if on_holiday:
            messages.append(_(
                "No activity can be logged on a public holiday:\n%s\n"
                "When logging several days at once, leave the public holidays out. "
                "Exceptional work on a public holiday must be logged by a timesheet administrator.",
                "\n".join(on_holiday),
            ))
        if messages:
            raise ValidationError("\n\n".join(messages))
