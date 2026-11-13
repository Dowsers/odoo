# -*- coding: utf-8 -*-
"""Generation of the yearly CIR activity report workbooks (one per employee)
and of the ZIP archive that bundles them.

The workbook layout follows the "Rapport mensuel d'activité - CIR" template:

* ``Synthèse <year>``: one row per project / task, one column per month
  (formulas pointing to the month sheets) and a yearly total;
* ``ReadMe``: usage notes, year and public holidays (used by formulas);
* one sheet per month (``Janvier`` ... ``Décembre``): employee header,
  one row per project / task, one column per day, totals, signature block
  and legend;
* ``Jours Feriés``: list of the public holidays of the year.

Times entered in hours in Odoo are converted to days using the working
hours per day of the employee's working schedule (1 day = 8 h by default).
"""
import io
import re
import zipfile
from calendar import monthrange
from datetime import date, datetime, timedelta

import pytz

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError
from odoo.tools import float_round

try:
    import xlsxwriter
except ImportError:  # pragma: no cover
    xlsxwriter = None

ADMIN_GROUP = 'hr_timesheet.group_timesheet_manager'

MONTHS_FR = [
    'Janvier', 'Février', 'Mars', 'Avril', 'Mai', 'Juin',
    'Juillet', 'Août', 'Septembre', 'Octobre', 'Novembre', 'Décembre',
]
ABSENCE_LABEL = 'Absence / Congés'
# Tasks whose name matches one of these patterns (case-insensitive) are
# reported on the "Absence / Congés" row by default.
ABSENCE_TASK_PATTERNS = ('congé', 'conge', 'férié', 'ferie', 'time off', 'absence')

# Month sheet layout (0-based indexes)
COL_PROJECT = 0        # A
COL_TASK = 1           # B
COL_DAY1 = 2           # C  (day 1) ... AG (day 31)
COL_TOTAL = 33         # AH
COL_OBS = 34           # AI
ROW_TITLE = 6          # row 7
ROW_HDR = 8            # rows 9-10 (merged)
ROW_HDR_VAL = 10       # rows 11-12 (merged)
ROW_COLSUM = 13        # row 14
ROW_DAYS = 14          # row 15
ROW_FIRST = 15         # row 16: first project row
# ReadMe layout: the holidays are listed from A9 (row index 8); the month
# sheets reference ReadMe!$A$9:$A$40 in their formulas.
README_HOL_FIRST_ROW = 8
README_HOL_LAST_ROW = 39

_INVALID_FILENAME_CHARS = re.compile(r'[\\/:*?"<>|\x00-\x1f]+')


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


def french_public_holidays(year):
    """French public holidays of ``year`` as a list of (date, label)."""
    easter = easter_date(year)
    return [
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


def split_employee_name(name):
    """Split an employee name into (first name, last name).

    Words written in capitals are considered as the last name
    ("Jean DE LA FONTAINE" -> ("Jean", "DE LA FONTAINE")).
    Without capitals, the first word is the first name.
    """
    tokens = (name or '').split()
    if not tokens:
        return '', ''

    def is_last(token):
        return len(token) > 1 and token.isupper()

    if any(is_last(t) for t in tokens) and not all(is_last(t) for t in tokens):
        first = ' '.join(t for t in tokens if not is_last(t))
        last = ' '.join(t for t in tokens if is_last(t))
        return first, last
    return tokens[0], ' '.join(tokens[1:])


def col_letter(col):
    """0-based column index -> Excel column letters."""
    return xlsxwriter.utility.xl_col_to_name(col)


def sheet_ref(name):
    """Quote a sheet name for use in a formula."""
    return "'%s'" % name.replace("'", "''")


class TimesheetCirExport(models.AbstractModel):
    _name = 'hr.timesheet.cir.export'
    _description = 'Timesheets CIR export (yearly workbook per employee)'

    # ------------------------------------------------------------------
    # Period / access helpers
    # ------------------------------------------------------------------
    @api.model
    def _default_period(self, today=None):
        """(year, month) of the last complete month before ``today``.

        On 2026-11-12 -> (2026, 10); on 2027-01-05 -> (2026, 12).
        """
        today = today or fields.Date.context_today(self)
        cutoff = today.replace(day=1) - timedelta(days=1)
        return cutoff.year, cutoff.month

    @api.model
    def _period_bounds(self, year, month):
        """First day of the year and last day of the cut-off month."""
        year, month = int(year), int(month)
        if not 1 <= month <= 12:
            raise UserError(_("The month must be between 1 and 12."))
        return date(year, 1, 1), date(year, month, monthrange(year, month)[1])

    @api.model
    def _check_access(self):
        if not self.env.user.has_group(ADMIN_GROUP):
            raise AccessError(_("Only timesheet administrators can export the CIR timesheets."))

    # ------------------------------------------------------------------
    # Data helpers
    # ------------------------------------------------------------------
    @api.model
    def _get_employees(self, date_from, date_to, employees=None):
        """Employees (active or not) having timesheets in the period, sorted by name."""
        domain = [
            ('project_id', '!=', False),
            ('employee_id', '!=', False),
            ('date', '>=', date_from),
            ('date', '<=', date_to),
        ]
        if employees:
            domain.append(('employee_id', 'in', employees.ids))
        groups = self.env['account.analytic.line']._read_group(domain, ['employee_id'])
        employee_ids = [employee.id for (employee,) in groups]
        found = self.env['hr.employee'].with_context(active_test=False).browse(employee_ids)
        return found.sorted(lambda e: (e.name or '').lower())

    @api.model
    def _get_default_absence_tasks(self):
        """Tasks reported on the "Absence / Congés" row: the company time off
        task (project_timesheet_holidays) and the tasks named like a leave."""
        Task = self.env['project.task'].with_context(active_test=False)
        tasks = Task
        companies = self.env.companies
        if 'leave_timesheet_task_id' in companies._fields:
            tasks |= companies.sudo().leave_timesheet_task_id.with_env(self.env)
        domain = ['|'] * (len(ABSENCE_TASK_PATTERNS) - 1)
        domain += [('name', 'ilike', pattern) for pattern in ABSENCE_TASK_PATTERNS]
        tasks |= Task.search(domain)
        return tasks.exists()

    @api.model
    def _get_hours_per_day(self, employee):
        calendar = (
            employee.resource_calendar_id
            or employee.company_id.resource_calendar_id
            or self.env.company.resource_calendar_id
        )
        return calendar.hours_per_day or 8.0

    @api.model
    def _get_holidays(self, year):
        """Public holidays of ``year``: French public holidays completed /
        overridden by the global leaves of the working schedules (Odoo).

        :return: sorted list of (date, label, source)
        """
        holidays = {day: (label, 'Calendrier') for day, label in french_public_holidays(year)}
        Leaves = self.env['resource.calendar.leaves'].sudo()
        domain = [
            ('resource_id', '=', False),
            ('date_from', '<=', datetime(year, 12, 31, 23, 59, 59)),
            ('date_to', '>=', datetime(year, 1, 1)),
            ('company_id', 'in', [False] + self.env.companies.ids),
        ]
        for leave in Leaves.search(domain):
            tz = pytz.timezone(leave.calendar_id.tz or leave.company_id.resource_calendar_id.tz or 'UTC')
            start = pytz.utc.localize(leave.date_from).astimezone(tz).date()
            stop = pytz.utc.localize(leave.date_to).astimezone(tz).date()
            day = max(start, date(year, 1, 1))
            while day <= min(stop, date(year, 12, 31)):
                holidays[day] = (leave.name or holidays.get(day, ('Fermeture',))[0], 'Odoo')
                day += timedelta(days=1)
        return [(day, label, source) for day, (label, source) in sorted(holidays.items())]

    @api.model
    def _collect_employee_data(self, employee, date_from, date_to, absence_task_ids):
        """Gather the timesheets of ``employee`` between the two dates.

        :return: dict with ``hours_per_day`` and ``rows``; each row is a dict
            ``{'is_absence', 'project', 'task', 'days': {date: days},
            'notes': {month: [descriptions]}}``, the absence row first and
            the other rows sorted by project then task.
        """
        Line = self.env['account.analytic.line']
        fields_to_read = ['date', 'project_id', 'task_id', 'unit_amount', 'name']
        for optional in ('holiday_id', 'global_leave_id'):
            if optional in Line._fields:
                fields_to_read.append(optional)
        lines = Line.search_read([
            ('employee_id', '=', employee.id),
            ('project_id', '!=', False),
            ('date', '>=', date_from),
            ('date', '<=', date_to),
        ], fields_to_read, order='date, id')

        hours_per_day = self._get_hours_per_day(employee)
        hours = {}      # (key, date) -> hours
        notes = {}      # (key, month) -> [description, ...]
        names = {}      # key -> (project name, task name)
        for line in lines:
            task_id = line['task_id'] and line['task_id'][0]
            is_absence = bool(
                line.get('holiday_id') or line.get('global_leave_id')
                or (task_id and task_id in absence_task_ids)
            )
            if is_absence:
                key = ('absence',)
                names[key] = (ABSENCE_LABEL, '')
            else:
                key = (line['project_id'][0], task_id or 0)
                names[key] = (line['project_id'][1], line['task_id'][1] if task_id else '')
            line_date = fields.Date.to_date(line['date'])
            hours[(key, line_date)] = hours.get((key, line_date), 0.0) + (line['unit_amount'] or 0.0)
            description = (line['name'] or '').strip()
            if description and description != '/':
                bucket = notes.setdefault((key, line_date.month), [])
                if description not in bucket:
                    bucket.append(description)

        rows = []
        for key, (project_name, task_name) in names.items():
            days = {}
            for (row_key, day), amount in hours.items():
                if row_key == key and amount:
                    days[day] = float_round(amount / hours_per_day, precision_digits=2)
            rows.append({
                'is_absence': key == ('absence',),
                'project': project_name,
                'task': task_name,
                'days': days,
                'notes': {month: texts for (row_key, month), texts in notes.items() if row_key == key},
            })
        rows.sort(key=lambda r: (not r['is_absence'], r['project'].lower(), r['task'].lower()))
        return {'hours_per_day': hours_per_day, 'rows': rows}

    # ------------------------------------------------------------------
    # Workbook
    # ------------------------------------------------------------------
    @api.model
    def _workbook_formats(self, wb):
        base = {'font_name': 'Tahoma', 'font_size': 10}
        hdr = dict(base, bg_color='#000000', font_color='#FFFFFF', align='center', valign='vcenter',
                   text_wrap=True, left=1, right=1, top=1, bottom=1)
        hdr8 = dict(hdr, font_size=8, bold=True, left=0, right=0, top=0, bottom=0)
        cell = dict(base, bottom=4, align='center')
        grey = '#D9D9D9'
        F = {
            'title': wb.add_format(dict(base, font_size=14, bold=True, align='center', valign='vcenter')),
            'hdr': wb.add_format(hdr),
            'hdr_val': wb.add_format(dict(base, bold=True, align='center', valign='vcenter', bottom=4, text_wrap=True)),
            'hdr_val_year': wb.add_format(dict(base, bold=True, align='center', valign='vcenter', bottom=4, num_format='0')),
            'hdr8': wb.add_format(dict(hdr8, align='left')),
            'hdr8_center': wb.add_format(dict(hdr8, align='center')),
            'datehdr': wb.add_format(dict(hdr, bold=True, num_format='d', text_wrap=False)),
            'nonexist_hdr': wb.add_format(dict(hdr, bg_color='#808080')),
            'colsum': wb.add_format(dict(base, font_size=8, align='center', num_format='0.##')),
            'label': wb.add_format(dict(base, font_size=8, align='left', valign='vcenter', text_wrap=True, bottom=4)),
            'label_abs': wb.add_format(dict(base, font_size=8, align='left', valign='vcenter', text_wrap=True, bottom=4, bg_color=grey)),
            'cell': wb.add_format(cell),
            'cell_abs': wb.add_format(dict(cell, bg_color=grey)),
            'nonexist': wb.add_format(dict(cell, bg_color='#808080')),
            'total': wb.add_format(dict(base, font_size=8, align='center', bottom=4, num_format='0.##')),
            'total_abs': wb.add_format(dict(base, font_size=8, align='center', bottom=4, num_format='0.##', bg_color=grey)),
            'obs': wb.add_format(dict(base, font_size=8, align='left', valign='vcenter', bottom=4)),
            'tot_label': wb.add_format(dict(base, align='right', bottom=4)),
            'tot_val': wb.add_format(dict(base, bold=True, align='center', bottom=4, num_format='0.##')),
            'tot_unit': wb.add_format(dict(base, bold=True, align='left', bottom=4)),
            'soit': wb.add_format({'font_name': 'Arial', 'font_size': 10, 'top': 4, 'bottom': 4}),
            'soit_val': wb.add_format({'font_name': 'Arial', 'font_size': 10, 'bold': True, 'italic': True,
                                       'align': 'center', 'top': 4, 'bottom': 4, 'num_format': '0.##'}),
            'soit_unit': wb.add_format({'font_name': 'Arial', 'font_size': 10, 'bold': True, 'italic': True, 'top': 4, 'bottom': 4}),
            'sig_hdr': wb.add_format(dict(base, bg_color='#000000', font_color='#FFFFFF', align='center')),
            'sig': wb.add_format(dict(base, align='left', valign='top')),
            'legend': wb.add_format(dict(base, align='left', valign='top', text_wrap=True)),
            'legend_sep': wb.add_format(dict(base, align='center')),
            'leg_red': wb.add_format(dict(base, bg_color='#C00000')),
            'leg_blue': wb.add_format(dict(base, bg_color='#00B0F0')),
            'leg_hatch': wb.add_format(dict(base, pattern=8, fg_color='#000000', bg_color='#FFFFFF')),
            'leg_grey': wb.add_format(dict(base, bg_color='#808080')),
            'cf_weekend': wb.add_format({'bg_color': '#00B0F0'}),
            'cf_holiday': wb.add_format({'pattern': 8, 'fg_color': '#000000', 'bg_color': '#FFFFFF'}),
            'cf_bad': wb.add_format({'bg_color': '#C00000', 'font_color': '#FFFFFF', 'bold': True}),
            # Synthesis sheet
            'syn_title': wb.add_format({'font_name': 'Arial Narrow', 'font_size': 20, 'align': 'left'}),
            'syn_sub': wb.add_format(dict(base, italic=True)),
            'syn_hdr': wb.add_format({'font_name': 'Arial Narrow', 'font_size': 11, 'bold': True, 'bg_color': '#000000',
                                      'font_color': '#FFFFFF', 'align': 'left', 'valign': 'vcenter', 'text_wrap': True,
                                      'left': 1, 'right': 1, 'top': 1, 'bottom': 1}),
            'syn_label': wb.add_format({'font_name': 'Arial Narrow', 'font_size': 11, 'align': 'left', 'valign': 'vcenter',
                                        'text_wrap': True, 'top': 4, 'bottom': 4}),
            'syn_label_abs': wb.add_format({'font_name': 'Arial Narrow', 'font_size': 11, 'align': 'left', 'valign': 'vcenter',
                                            'text_wrap': True, 'top': 4, 'bottom': 4, 'bg_color': grey}),
            'syn_val': wb.add_format(dict(base, font_size=8, align='center', valign='vcenter', top=4, bottom=4, num_format='0.##')),
            'syn_val_abs': wb.add_format(dict(base, font_size=8, align='center', valign='vcenter', top=4, bottom=4, num_format='0.##', bg_color=grey)),
            'syn_total': wb.add_format(dict(base, font_size=8, bold=True, align='center', valign='vcenter', top=1, bottom=1, num_format='0.##')),
            # ReadMe / holidays sheets
            'rm_title': wb.add_format(dict(base, bold=True, font_size=12)),
            'rm_num': wb.add_format(dict(base, align='right', valign='top')),
            'rm_text': wb.add_format(dict(base, text_wrap=True, valign='top')),
            'rm_warn': wb.add_format(dict(base, bold=True, font_color='#C00000')),
            'rm_label': wb.add_format(dict(base, bold=True)),
            'rm_year': wb.add_format(dict(base, bold=True, num_format='0')),
            'rm_date': wb.add_format(dict(base, num_format='dd/mm/yyyy')),
            'rm_plain': wb.add_format(base),
            'hol_hdr': wb.add_format(dict(hdr, text_wrap=False)),
            'hol_date': wb.add_format(dict(base, num_format='dd/mm/yyyy', bottom=4)),
            'hol_text': wb.add_format(dict(base, bottom=4)),
        }
        return F

    @api.model
    def _generate_workbook(self, employee, year, month, data, holidays=None):
        """Build the yearly workbook of ``employee`` and return its bytes.

        :param month: last month (1-12) whose timesheets are included; the
            sheets of the following months are generated empty.
        """
        if xlsxwriter is None:  # pragma: no cover
            raise UserError(_("The Python library xlsxwriter is required to export the timesheets."))
        year, month = int(year), int(month)
        holidays = holidays if holidays is not None else self._get_holidays(year)
        holiday_dates = {day for day, _label, _source in holidays}
        rows = data['rows']
        hours_per_day = data['hours_per_day']
        employee = employee.sudo()
        first_name, last_name = split_employee_name(employee.name)
        header = {
            'last_name': last_name,
            'first_name': first_name,
            'matricule': employee.barcode or '',
            'hours_per_day': hours_per_day,
            'phone': employee.work_phone or '',
        }
        date_from, date_to = self._period_bounds(year, month)

        output = io.BytesIO()
        wb = xlsxwriter.Workbook(output, {'in_memory': True, 'remove_timezone': True})
        wb.set_properties({
            'title': "Rapport mensuel d'activité - CIR %s - %s" % (year, employee.name),
            'subject': 'Feuilles de temps %s' % year,
            'author': self.env.company.name or '',
            'comments': 'Généré depuis Odoo le %s' % fields.Date.context_today(self).strftime('%d/%m/%Y'),
        })
        F = self._workbook_formats(wb)
        synthesis_name = 'Synthèse %s' % year
        ws_synthesis = wb.add_worksheet(synthesis_name)
        ws_readme = wb.add_worksheet('ReadMe')
        month_sheets = [wb.add_worksheet(name) for name in MONTHS_FR]
        ws_holidays = wb.add_worksheet('Jours Feriés')

        row_month_totals = {}   # (row index, month) -> days of the month (cached values)
        for index, ws in enumerate(month_sheets):
            totals = self._write_month_sheet(
                ws, F, year, index + 1, rows, header, holiday_dates, include=(index + 1) <= month)
            for row_index, value in enumerate(totals):
                row_month_totals[(row_index, index + 1)] = value

        self._write_synthesis_sheet(ws_synthesis, F, year, employee, rows, row_month_totals, date_from, date_to, hours_per_day)
        self._write_readme_sheet(ws_readme, F, year, hours_per_day, holidays, date_from, date_to)
        self._write_holidays_sheet(ws_holidays, F, holidays)
        ws_synthesis.activate()
        wb.close()
        return output.getvalue()

    @api.model
    def _write_month_sheet(self, ws, F, year, month, rows, header, holiday_dates, include=True):
        """Write one month sheet; return the cached total of each row."""
        ndays = monthrange(year, month)[1]
        n = len(rows)
        row_last = ROW_FIRST + n - 1
        row_tot = ROW_FIRST + n          # "Total du mois"
        row_soit = row_tot + 1
        row_sig = row_tot + 3            # signature block (3 rows)
        row_leg = row_sig + 7            # legend (2 rows)
        month_name = MONTHS_FR[month - 1]

        ws.set_column(COL_PROJECT, COL_PROJECT, 24)
        ws.set_column(COL_TASK, COL_TASK, 34)
        ws.set_column(COL_DAY1, COL_DAY1 + 30, 3.7)
        ws.set_column(COL_TOTAL, COL_TOTAL, 12.4)
        ws.set_column(COL_OBS, COL_OBS, 48)
        ws.set_row(ROW_TITLE, 20)
        ws.set_row(ROW_HDR, 12.6)
        ws.set_row(ROW_HDR + 1, 12.6)
        ws.set_row(ROW_HDR_VAL, 13)
        ws.set_row(ROW_HDR_VAL + 1, 13)

        # Title
        ws.merge_range(ROW_TITLE, COL_PROJECT, ROW_TITLE, COL_OBS,
                       "Rapport mensuel d'activité - %s %s" % (month_name, year), F['title'])

        # Employee header (labels on rows 9-10, values on rows 11-12)
        blocks = [
            (0, 1, 'Nom', header['last_name'], F['hdr_val']),
            (2, 9, 'Prénom', header['first_name'], F['hdr_val']),
            (10, 16, 'Matricule', header['matricule'], F['hdr_val']),
            (17, 21, 'Heures / jour', header['hours_per_day'], F['hdr_val']),
            (22, 26, 'Mois', month_name, F['hdr_val']),
            (27, 31, 'Année', year, F['hdr_val_year']),
            (32, 33, 'Nb jours ouvrés', None, F['hdr_val']),
            (34, 34, 'Tél. Bureau', header['phone'], F['hdr_val']),
        ]
        for col1, col2, label, value, fmt in blocks:
            ws.merge_range(ROW_HDR, col1, ROW_HDR + 1, col2, label, F['hdr'])
            ws.merge_range(ROW_HDR_VAL, col1, ROW_HDR_VAL + 1, col2, '', fmt)
            if value is not None:
                ws.write(ROW_HDR_VAL, col1, value, fmt)
        # Working days of the month (NETWORKDAYS with the holidays of the ReadMe sheet)
        working_days = sum(
            1 for d in range(1, ndays + 1)
            if date(year, month, d).weekday() < 5 and date(year, month, d) not in holiday_dates
        )
        ws.write_formula(
            ROW_HDR_VAL, 32,
            '=NETWORKDAYS(DATE(%d,%d,1),DATE(%d,%d,%d),ReadMe!$A$%d:$A$%d)' % (
                year, month, year, month, ndays, README_HOL_FIRST_ROW + 1, README_HOL_LAST_ROW + 1),
            F['hdr_val'], working_days)

        # Day headers (row 15) and project / task labels
        ws.write(ROW_DAYS, COL_PROJECT, 'Projet', F['hdr8'])
        ws.write(ROW_DAYS, COL_TASK, 'Etape', F['hdr8_center'])
        for d in range(1, 32):
            col = COL_DAY1 + d - 1
            if d <= ndays:
                ws.write_datetime(ROW_DAYS, col, datetime(year, month, d), F['datehdr'])
            else:
                ws.write_blank(ROW_DAYS, col, None, F['nonexist_hdr'])
        ws.write(ROW_DAYS, COL_TOTAL, 'Total jours', F['hdr8_center'])
        ws.write(ROW_DAYS, COL_OBS, 'Observations', F['hdr8_center'])

        # Project rows
        row_totals = []
        column_totals = [0.0] * 32
        for i, row in enumerate(rows):
            r = ROW_FIRST + i
            is_abs = row['is_absence']
            ws.write(r, COL_PROJECT, row['project'], F['label_abs'] if is_abs else F['label'])
            ws.write(r, COL_TASK, row['task'], F['label_abs'] if is_abs else F['label'])
            total = 0.0
            for d in range(1, 32):
                col = COL_DAY1 + d - 1
                if d > ndays:
                    ws.write_blank(r, col, None, F['nonexist'])
                    continue
                value = row['days'].get(date(year, month, d)) if include else None
                fmt = F['cell_abs'] if is_abs else F['cell']
                if value:
                    ws.write_number(r, col, value, fmt)
                    total += value
                    column_totals[d] += value
                else:
                    ws.write_blank(r, col, None, fmt)
            total = float_round(total, precision_digits=2)
            row_totals.append(total)
            ws.write_formula(
                r, COL_TOTAL,
                '=SUM(%s%d:%s%d)' % (col_letter(COL_DAY1), r + 1, col_letter(COL_DAY1 + 30), r + 1),
                F['total_abs'] if is_abs else F['total'], total)
            observations = row['notes'].get(month, []) if include else []
            text = ' ; '.join(observations)
            if len(text) > 250:
                text = text[:247] + '...'
            ws.write(r, COL_OBS, text, F['obs'])

        # Column totals (row 14)
        if n:
            for d in range(1, ndays + 1):
                col = COL_DAY1 + d - 1
                letter = col_letter(col)
                ws.write_formula(
                    ROW_COLSUM, col,
                    '=SUM(%s$%d:%s$%d)' % (letter, ROW_FIRST + 1, letter, row_last + 1),
                    F['colsum'], float_round(column_totals[d], precision_digits=2))

        # Month total and hours
        month_total = float_round(sum(row_totals), precision_digits=2)
        ws.merge_range(row_tot, 28, row_tot, 32, 'Total du mois : ', F['tot_label'])
        total_formula = '=SUM(%s%d:%s%d)' % (col_letter(COL_TOTAL), ROW_FIRST + 1, col_letter(COL_TOTAL), row_last + 1) if n else '=0'
        ws.write_formula(row_tot, COL_TOTAL, total_formula, F['tot_val'], month_total)
        ws.write(row_tot, COL_OBS, 'jours', F['tot_unit'])
        ws.write(row_soit, 31, 'Soit', F['soit'])
        ws.write_formula(
            row_soit, COL_TOTAL,
            '=%s%d*$R$%d' % (col_letter(COL_TOTAL), row_tot + 1, ROW_HDR_VAL + 1),
            F['soit_val'], float_round(month_total * header['hours_per_day'], precision_digits=2))
        ws.write(row_soit, COL_OBS, 'heures', F['soit_unit'])

        # Signature block
        ws.merge_range(row_sig, 0, row_sig, 8, 'COLLABORATEUR', F['sig_hdr'])
        ws.merge_range(row_sig, 9, row_sig, 25, 'RESPONSABLE', F['sig_hdr'])
        ws.merge_range(row_sig, 26, row_sig, 34, 'SAISIE', F['sig_hdr'])
        for col in (0, 9, 26):
            ws.write(row_sig + 1, col, 'Date', F['sig'])
            ws.write(row_sig + 2, col, 'Visa', F['sig'])
        ws.set_row(row_sig + 2, 30)

        # Legend
        ws.write_blank(row_leg, 2, None, F['leg_red'])
        ws.write(row_leg, 3, ':', F['legend_sep'])
        ws.merge_range(row_leg, 4, row_leg + 1, 12, 'Valeur incorrecte : mettre 1 ou 0,5 ; ou nbre de jours ouvrés.', F['legend'])
        ws.write_blank(row_leg, 14, None, F['leg_blue'])
        ws.write(row_leg, 15, ':', F['legend_sep'])
        ws.merge_range(row_leg, 16, row_leg, 22, 'Samedi et Dimanche', F['legend'])
        ws.write_blank(row_leg, 24, None, F['leg_hatch'])
        ws.write(row_leg, 25, ':', F['legend_sep'])
        ws.merge_range(row_leg, 26, row_leg, 28, 'Jours fériés', F['legend'])
        ws.write_blank(row_leg, 30, None, F['leg_grey'])
        ws.write(row_leg, 31, ':', F['legend_sep'])
        ws.merge_range(row_leg, 32, row_leg, 33, 'Jours inexistants', F['legend'])

        # Conditional formats on the day cells (weekends, holidays, unexpected values)
        if n:
            first_cell = '%s%d' % (col_letter(COL_DAY1), ROW_FIRST + 1)
            day_header = '%s$%d' % (col_letter(COL_DAY1), ROW_DAYS + 1)
            cf_range = (ROW_FIRST, COL_DAY1, row_last, COL_DAY1 + ndays - 1)
            ws.conditional_format(*cf_range, {
                'type': 'formula', 'criteria': '=WEEKDAY(%s,2)>=6' % day_header,
                'format': F['cf_weekend'], 'stop_if_true': True})
            ws.conditional_format(*cf_range, {
                'type': 'formula',
                'criteria': '=COUNTIF(ReadMe!$A$%d:$A$%d,%s)>0' % (
                    README_HOL_FIRST_ROW + 1, README_HOL_LAST_ROW + 1, day_header),
                'format': F['cf_holiday'], 'stop_if_true': True})
            ws.conditional_format(*cf_range, {
                'type': 'formula', 'criteria': '=AND(%s<>1,%s<>0.5,%s<>"")' % (first_cell, first_cell, first_cell),
                'format': F['cf_bad']})

        # Page setup
        ws.set_landscape()
        ws.set_paper(9)
        ws.fit_to_pages(1, 1)
        ws.set_margins(left=0.3, right=0.3, top=0.4, bottom=0.4)
        ws.print_area(0, 0, row_leg + 1, COL_OBS)
        ws.hide_gridlines(2)
        ws.set_zoom(85)
        return row_totals

    @api.model
    def _write_synthesis_sheet(self, ws, F, year, employee, rows, row_month_totals, date_from, date_to, hours_per_day=8.0):
        n = len(rows)
        COL_P, COL_T, COL_M1 = 1, 2, 3          # B, C, D..O
        COL_TOT = COL_M1 + 12                   # P
        ROW_H = 9                               # row 10
        ROW_R1 = 10                             # row 11
        row_total = ROW_R1 + n

        ws.set_column(0, 0, 3)
        ws.set_column(COL_P, COL_P, 26)
        ws.set_column(COL_T, COL_T, 36)
        ws.set_column(COL_M1, COL_M1 + 11, 9.5)
        ws.set_column(COL_TOT, COL_TOT, 13)
        ws.set_row(4, 25)
        ws.set_row(ROW_H, 28)

        ws.write(4, COL_P, "Synthèse du temps passé par projet sur l'année %s" % year, F['syn_title'])
        ws.write(5, COL_P, '%s - période du %s au %s' % (
            employee.name, date_from.strftime('%d/%m/%Y'), date_to.strftime('%d/%m/%Y')), F['syn_sub'])
        ws.write(6, COL_P, 'Généré depuis Odoo le %s - valeurs en jours (1 jour = %g h)' % (
            fields.Date.context_today(self).strftime('%d/%m/%Y'), hours_per_day), F['syn_sub'])

        ws.write(ROW_H, COL_P, 'Projet', F['syn_hdr'])
        ws.write(ROW_H, COL_T, 'Etape', F['syn_hdr'])
        for m in range(12):
            ws.write(ROW_H, COL_M1 + m, MONTHS_FR[m], F['syn_hdr'])
        ws.write(ROW_H, COL_TOT, 'Total jours par projet', F['syn_hdr'])

        month_sums = [0.0] * 12
        grand_total = 0.0
        for i, row in enumerate(rows):
            r = ROW_R1 + i
            is_abs = row['is_absence']
            ws.write(r, COL_P, row['project'], F['syn_label_abs'] if is_abs else F['syn_label'])
            ws.write(r, COL_T, row['task'], F['syn_label_abs'] if is_abs else F['syn_label'])
            line_total = 0.0
            for m in range(12):
                value = row_month_totals.get((i, m + 1), 0.0)
                ws.write_formula(
                    r, COL_M1 + m,
                    '=%s!%s%d' % (sheet_ref(MONTHS_FR[m]), col_letter(COL_TOTAL), ROW_FIRST + i + 1),
                    F['syn_val_abs'] if is_abs else F['syn_val'], value)
                line_total += value
                if not is_abs:
                    month_sums[m] += value
            line_total = float_round(line_total, precision_digits=2)
            ws.write_formula(
                r, COL_TOT,
                '=SUM(%s%d:%s%d)' % (col_letter(COL_M1), r + 1, col_letter(COL_M1 + 11), r + 1),
                F['syn_val_abs'] if is_abs else F['syn_val'], line_total)
            if not is_abs:
                grand_total += line_total

        # TOTAL row (absences excluded, like the template)
        first_project_row = ROW_R1 + (1 if rows and rows[0]['is_absence'] else 0)
        last_project_row = ROW_R1 + n - 1
        ws.write(row_total, COL_P, 'TOTAL', F['syn_hdr'])
        ws.write(row_total, COL_T, '(hors absences / congés)', F['syn_hdr'])
        for m in range(13):
            col = COL_M1 + m
            value = float_round(month_sums[m], precision_digits=2) if m < 12 else float_round(grand_total, precision_digits=2)
            if last_project_row >= first_project_row:
                formula = '=SUM(%s%d:%s%d)' % (col_letter(col), first_project_row + 1, col_letter(col), last_project_row + 1)
            else:
                formula = '=0'
            ws.write_formula(row_total, col, formula, F['syn_total'], value)

        ws.set_landscape()
        ws.set_paper(9)
        ws.fit_to_pages(1, 1)
        ws.print_area(0, COL_P, row_total, COL_TOT)
        ws.hide_gridlines(2)
        ws.set_zoom(85)

    @api.model
    def _write_readme_sheet(self, ws, F, year, hours_per_day, holidays, date_from, date_to):
        ws.set_column(0, 0, 20)
        ws.set_column(1, 1, 110)
        ws.write(1, 1, 'UTILISATION DU FICHIER DE SUIVI DU TEMPS', F['rm_title'])
        notes = [
            "Fichier généré automatiquement depuis les feuilles de temps Odoo le %s, pour la période du %s au %s "
            "(année en cours arrêtée au dernier mois révolu)." % (
                fields.Date.context_today(self).strftime('%d/%m/%Y'),
                date_from.strftime('%d/%m/%Y'), date_to.strftime('%d/%m/%Y')),
            "Les temps saisis en heures dans Odoo sont convertis en jours (1 jour = %s h, horaire de travail du collaborateur) : "
            "1 = journée complète, 0,5 = demi-journée. Toute autre valeur est signalée en rouge dans les onglets mensuels." % (
                ('%g' % hours_per_day)),
            "Chaque onglet mensuel reprend, par projet et étape (tâche Odoo), les jours passés par date ; la colonne Observations "
            "reprend les descriptions saisies. L'onglet Synthèse totalise les mois ; la ligne « Absence / Congés » n'est pas "
            "comptée dans le TOTAL.",
        ]
        for i, text in enumerate(notes):
            ws.write(2 + i, 0, '%d.' % (i + 1), F['rm_num'])
            ws.write(2 + i, 1, text, F['rm_text'])
            ws.set_row(2 + i, 30)
        ws.write(5, 0, 'NE PAS SUPPRIMER', F['rm_warn'])
        ws.write(6, 0, 'Année', F['rm_label'])
        ws.write_number(6, 1, year, F['rm_year'])
        ws.write(7, 0, 'Jours fériés %s' % year, F['rm_label'])
        for i, (day, label, _source) in enumerate(holidays[:README_HOL_LAST_ROW - README_HOL_FIRST_ROW + 1]):
            ws.write_datetime(README_HOL_FIRST_ROW + i, 0, datetime(day.year, day.month, day.day), F['rm_date'])
            ws.write(README_HOL_FIRST_ROW + i, 1, label, F['rm_plain'])

    @api.model
    def _write_holidays_sheet(self, ws, F, holidays):
        ws.set_column(0, 0, 14)
        ws.set_column(1, 1, 30)
        ws.set_column(2, 2, 14)
        ws.write(0, 0, 'Date', F['hol_hdr'])
        ws.write(0, 1, 'Jour férié', F['hol_hdr'])
        ws.write(0, 2, 'Source', F['hol_hdr'])
        for i, (day, label, source) in enumerate(holidays):
            ws.write_datetime(1 + i, 0, datetime(day.year, day.month, day.day), F['hol_date'])
            ws.write(1 + i, 1, label, F['hol_text'])
            ws.write(1 + i, 2, source, F['hol_text'])

    # ------------------------------------------------------------------
    # ZIP
    # ------------------------------------------------------------------
    @api.model
    def _workbook_filename(self, year, employee, used_names):
        name = _INVALID_FILENAME_CHARS.sub(' ', employee.name or '').strip()
        name = re.sub(r'\s+', ' ', name) or 'employe-%d' % employee.id
        base = "Rapport mensuel d'activité - CIR %s - %s" % (year, name)
        filename = base + '.xlsx'
        if filename.lower() in used_names:
            filename = '%s (%d).xlsx' % (base, employee.id)
        used_names.add(filename.lower())
        return filename

    @api.model
    def _generate_zip(self, year, month, employees=None, absence_tasks=None):
        """Build the ZIP archive; return ``(content, filename)``."""
        self._check_access()
        year, month = int(year), int(month)
        date_from, date_to = self._period_bounds(year, month)
        employees = self._get_employees(date_from, date_to, employees)
        if not employees:
            raise UserError(_(
                "No timesheet found between %(date_from)s and %(date_to)s.",
                date_from=date_from.strftime('%d/%m/%Y'), date_to=date_to.strftime('%d/%m/%Y')))
        if absence_tasks is None:
            absence_tasks = self._get_default_absence_tasks()
        absence_task_ids = set(absence_tasks.ids)
        holidays = self._get_holidays(year)

        buffer = io.BytesIO()
        used_names = set()
        with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as archive:
            for employee in employees:
                data = self._collect_employee_data(employee, date_from, date_to, absence_task_ids)
                content = self._generate_workbook(employee, year, month, data, holidays)
                archive.writestr('%d/%s' % (year, self._workbook_filename(year, employee, used_names)), content)
        return buffer.getvalue(), 'Fiche_de_temps_%d.zip' % year
