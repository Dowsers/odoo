# -*- coding: utf-8 -*-
import io
import zipfile
from datetime import date, datetime

from odoo import http
from odoo.exceptions import AccessError, UserError
from odoo.tests import HttpCase, TransactionCase, tagged

from ..models.timesheet_cir_export import easter_date, french_public_holidays, split_employee_name

try:
    import openpyxl
except ImportError:  # pragma: no cover
    openpyxl = None

YEAR = 2024


def excel_serial(day):
    """Excel serial number of a date (what openpyxl returns for cells formatted with 'd')."""
    return (day - date(1899, 12, 30)).days
ADMIN_GROUP = 'hr_timesheet.group_timesheet_manager'
JEAN_FILE = "%d/Rapport mensuel d'activité - CIR %d - Jean DE LA FONTAINE.xlsx" % (YEAR, YEAR)
PAUL_FILE = "%d/Rapport mensuel d'activité - CIR %d - Paul Martin.xlsx" % (YEAR, YEAR)


class TestCirExportCommon(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env = cls.env(context=dict(cls.env.context, tracking_disable=True, no_reset_password=True))
        cls.company = cls.env.company
        cls.calendar = cls.env['resource.calendar'].create({
            'name': 'Test 40h', 'hours_per_day': 8.0, 'company_id': cls.company.id,
        })
        cls.manager = cls.env['res.users'].create({
            'name': 'Timesheet Admin', 'login': 'cir_admin', 'password': 'cir_admin_pwd_123',
            'email': 'cir_admin@example.com',
            'group_ids': [(6, 0, [cls.env.ref('base.group_user').id, cls.env.ref(ADMIN_GROUP).id])],
        })
        cls.plain_user = cls.env['res.users'].create({
            'name': 'Timesheet User', 'login': 'cir_user', 'password': 'cir_user_pwd_123',
            'email': 'cir_user@example.com',
            'group_ids': [(6, 0, [cls.env.ref('base.group_user').id,
                                  cls.env.ref('hr_timesheet.group_hr_timesheet_user').id])],
        })
        Employee = cls.env['hr.employee']
        cls.emp_jean = Employee.create({
            'name': 'Jean DE LA FONTAINE', 'barcode': 'M042', 'work_phone': '01 02 03 04 05',
            'resource_calendar_id': cls.calendar.id, 'company_id': cls.company.id,
        })
        cls.emp_paul = Employee.create({
            'name': 'Paul Martin', 'resource_calendar_id': cls.calendar.id, 'company_id': cls.company.id,
        })
        cls.emp_nobody = Employee.create({
            'name': 'Zoé SANS', 'resource_calendar_id': cls.calendar.id, 'company_id': cls.company.id,
        })
        cls.employees = cls.emp_jean + cls.emp_paul + cls.emp_nobody

        plan = cls.env['account.analytic.plan'].create({'name': 'CIR test plan'})
        Project = cls.env['project.project']
        cls.project_rd = Project.create({
            'name': 'Recherche', 'allow_timesheets': True, 'company_id': cls.company.id,
            'account_id': cls.env['account.analytic.account'].create({
                'name': 'Recherche', 'plan_id': plan.id, 'company_id': cls.company.id}).id,
        })
        cls.project_gen = Project.create({
            'name': 'Général', 'allow_timesheets': True, 'company_id': cls.company.id,
            'account_id': cls.env['account.analytic.account'].create({
                'name': 'Général', 'plan_id': plan.id, 'company_id': cls.company.id}).id,
        })
        Task = cls.env['project.task']
        cls.task_a = Task.create({'name': 'Tâche A', 'project_id': cls.project_rd.id})
        cls.task_b = Task.create({'name': 'Tâche B', 'project_id': cls.project_rd.id})
        cls.task_leave = Task.create({'name': 'Congés', 'project_id': cls.project_gen.id})

        def line(employee, day, hours, project, task=None, name='/'):
            return {
                'employee_id': employee.id, 'date': day, 'unit_amount': hours, 'name': name,
                'project_id': project.id, 'task_id': task.id if task else False,
            }
        cls.env['account.analytic.line'].create([
            line(cls.emp_jean, date(YEAR, 1, 2), 8, cls.project_rd, cls.task_a, 'Analyse'),
            line(cls.emp_jean, date(YEAR, 1, 3), 4, cls.project_rd, cls.task_a, 'Analyse'),
            line(cls.emp_jean, date(YEAR, 1, 3), 4, cls.project_rd, cls.task_b, 'Tests'),
            line(cls.emp_jean, date(YEAR, 1, 15), 0, cls.project_rd, cls.task_b),
            line(cls.emp_jean, date(YEAR, 2, 14), 8, cls.project_rd, cls.task_b),
            line(cls.emp_jean, date(YEAR, 3, 1), 2, cls.project_rd, cls.task_a),
            line(cls.emp_jean, date(YEAR, 3, 4), 8, cls.project_gen, cls.task_leave),
            # after the cut-off month (March): must not be exported
            line(cls.emp_jean, date(YEAR, 4, 2), 8, cls.project_rd, cls.task_a),
            line(cls.emp_paul, date(YEAR, 2, 5), 8, cls.project_rd, None, 'Lecture'),
        ])
        cls.exporter = cls.env['hr.timesheet.cir.export'].with_user(cls.manager)

    def _generate(self, month=3, employees=None):
        content, filename = self.exporter._generate_zip(
            YEAR, month, employees if employees is not None else self.employees)
        return zipfile.ZipFile(io.BytesIO(content)), filename

    def _open(self, archive, name, data_only=False):
        return openpyxl.load_workbook(io.BytesIO(archive.read(name)), data_only=data_only)


@tagged('post_install', '-at_install')
class TestCirExport(TestCirExportCommon):

    def test_default_period(self):
        exporter = self.env['hr.timesheet.cir.export']
        self.assertEqual(exporter._default_period(date(2026, 11, 12)), (2026, 10))
        self.assertEqual(exporter._default_period(date(2027, 1, 5)), (2026, 12))
        self.assertEqual(exporter._default_period(date(2026, 3, 1)), (2026, 2))
        self.assertEqual(exporter._period_bounds(2024, 2), (date(2024, 1, 1), date(2024, 2, 29)))

    def test_helpers(self):
        self.assertEqual(split_employee_name('Jean DE LA FONTAINE'), ('Jean', 'DE LA FONTAINE'))
        self.assertEqual(split_employee_name('Léa ÉTIENNE'), ('Léa', 'ÉTIENNE'))
        self.assertEqual(split_employee_name('Paul Martin'), ('Paul', 'Martin'))
        self.assertEqual(split_employee_name('JEAN DUPONT'), ('JEAN', 'DUPONT'))
        self.assertEqual(split_employee_name(''), ('', ''))
        self.assertEqual(easter_date(2024), date(2024, 3, 31))
        self.assertEqual(easter_date(2025), date(2025, 4, 20))
        holidays = dict(french_public_holidays(2025))
        self.assertEqual(holidays[date(2025, 4, 21)], 'Lundi de Pâques')
        self.assertEqual(holidays[date(2025, 5, 29)], 'Ascension')
        self.assertEqual(holidays[date(2025, 6, 9)], 'Lundi de Pentecôte')
        self.assertIn(self.task_leave, self.env['hr.timesheet.cir.export']._get_default_absence_tasks())

    def test_access(self):
        with self.assertRaises(AccessError):
            self.env['hr.timesheet.cir.export'].with_user(self.plain_user)._generate_zip(YEAR, 3)
        wizard = self.env['hr.timesheet.cir.export.wizard']
        action = self.env.ref('hr_timesheet.timesheet_action_all')
        self.assertTrue(wizard.with_user(self.manager).is_export_button_visible(action.id))
        self.assertFalse(wizard.with_user(self.manager).is_export_button_visible(
            self.env.ref('hr_timesheet.act_hr_timesheet_line').id))
        self.assertFalse(wizard.with_user(self.plain_user).is_export_button_visible(action.id))

    def test_zip_content(self):
        archive, filename = self._generate()
        self.assertEqual(filename, 'Fiche_de_temps_%d.zip' % YEAR)
        names = sorted(archive.namelist())
        self.assertEqual(names, sorted([JEAN_FILE, PAUL_FILE]), "one workbook per employee having timesheets")
        with self.assertRaises(UserError):
            self.exporter._generate_zip(YEAR, 3, self.emp_nobody)

    def test_workbook_layout(self):
        if openpyxl is None:
            self.skipTest('openpyxl is not available')
        archive, _filename = self._generate()
        wb = self._open(archive, JEAN_FILE)
        self.assertEqual(wb.sheetnames, [
            'Synthèse %d' % YEAR, 'ReadMe', 'Janvier', 'Février', 'Mars', 'Avril', 'Mai', 'Juin', 'Juillet',
            'Août', 'Septembre', 'Octobre', 'Novembre', 'Décembre', 'Jours Feriés'])

        jan = wb['Janvier']
        self.assertEqual(jan['A11'].value, 'DE LA FONTAINE')
        self.assertEqual(jan['C11'].value, 'Jean')
        self.assertEqual(jan['K11'].value, 'M042')
        self.assertEqual(jan['R11'].value, 8)
        self.assertEqual(jan['W11'].value, 'Janvier')
        self.assertEqual(jan['AB11'].value, YEAR)
        self.assertEqual(jan['AI11'].value, '01 02 03 04 05')
        self.assertEqual(jan['AG11'].value, '=NETWORKDAYS(DATE(2024,1,1),DATE(2024,1,31),ReadMe!$A$9:$A$40)')
        self.assertEqual(jan['A15'].value, 'Projet')
        self.assertEqual(jan['B15'].value, 'Etape')
        self.assertEqual(jan['C15'].value, excel_serial(date(YEAR, 1, 1)), 'day headers are dates')
        self.assertEqual(jan['C15'].number_format, 'd')
        self.assertEqual(jan['AG15'].value, excel_serial(date(YEAR, 1, 31)))
        # rows: absence first, then projects / tasks sorted by name
        self.assertEqual([(jan.cell(r, 1).value, jan.cell(r, 2).value) for r in (16, 17, 18)], [
            ('Absence / Congés', None), ('Recherche', 'Tâche A'), ('Recherche', 'Tâche B')])
        self.assertEqual(jan['D17'].value, 1, '8 h on January 2nd = 1 day')
        self.assertEqual(jan['E17'].value, 0.5, '4 h on January 3rd = half a day')
        self.assertEqual(jan['E18'].value, 0.5)
        self.assertIsNone(jan['P18'].value, 'a 0 h line leaves the cell empty')
        self.assertEqual(jan['AH17'].value, '=SUM(C17:AG17)')
        self.assertEqual(jan['AI17'].value, 'Analyse')
        self.assertEqual(jan['AH19'].value, '=SUM(AH16:AH18)', 'month total right after the last project row')
        self.assertEqual(jan['AI19'].value, 'jours')
        self.assertEqual(jan['AH20'].value, '=AH19*$R$11')
        self.assertEqual(jan['A22'].value, 'COLLABORATEUR')
        self.assertEqual(jan['E29'].value, 'Valeur incorrecte : mettre 1 ou 0,5 ; ou nbre de jours ouvrés.')

        feb = wb['Février']
        self.assertEqual(feb['P18'].value, 1, '8 h on February 14th')
        self.assertIsNone(feb['AG15'].value, 'no 31st in February')
        mar = wb['Mars']
        self.assertEqual(mar['C17'].value, 0.25, '2 h = 0.25 day')
        self.assertEqual(mar['F16'].value, 1, 'leave task reported on the absence row')
        apr = wb['Avril']
        self.assertIsNone(apr['D17'].value, 'timesheets after the cut-off month are not exported')

        syn = wb['Synthèse %d' % YEAR]
        self.assertEqual(syn['B10'].value, 'Projet')
        self.assertEqual(syn['C10'].value, 'Etape')
        self.assertEqual(syn['D10'].value, 'Janvier')
        self.assertEqual(syn['O10'].value, 'Décembre')
        self.assertEqual(syn['B11'].value, 'Absence / Congés')
        self.assertEqual(syn['B12'].value, 'Recherche')
        self.assertEqual(syn['C12'].value, 'Tâche A')
        self.assertEqual(syn['D12'].value, "='Janvier'!AH17")
        self.assertEqual(syn['P12'].value, '=SUM(D12:O12)')
        self.assertEqual(syn['B14'].value, 'TOTAL')
        self.assertEqual(syn['P14'].value, '=SUM(P12:P13)', 'absence row excluded from the total')

        readme = wb['ReadMe']
        self.assertEqual(readme['B7'].value, YEAR)
        self.assertEqual(readme['A9'].value, datetime(YEAR, 1, 1))
        self.assertEqual(readme['A10'].value, datetime(YEAR, 4, 1), 'Easter Monday 2024')
        holidays = wb['Jours Feriés']
        self.assertEqual(holidays['A1'].value, 'Date')
        self.assertIn(datetime(YEAR, 5, 20), [holidays.cell(r, 1).value for r in range(2, 20)], 'Whit Monday 2024')

        paul = self._open(archive, PAUL_FILE)
        jan = paul['Janvier']
        self.assertEqual((jan['A11'].value, jan['C11'].value), ('Martin', 'Paul'))
        self.assertEqual((jan['A16'].value, jan['B16'].value), ('Recherche', None), 'timesheet without task')
        self.assertEqual(paul['Février']['G16'].value, 1)
        self.assertEqual(paul['Février']['AI16'].value, 'Lecture')

    def test_cached_values(self):
        """The formula results are stored so that viewers which do not
        recalculate (previews, python readers) show the right numbers."""
        if openpyxl is None:
            self.skipTest('openpyxl is not available')
        archive, _filename = self._generate()
        wb = self._open(archive, JEAN_FILE, data_only=True)
        jan = wb['Janvier']
        self.assertEqual(jan['AH17'].value, 1.5)
        self.assertEqual(jan['AH18'].value, 0.5)
        self.assertEqual(jan['AH19'].value, 2)
        self.assertEqual(jan['AH20'].value, 16, '2 days * 8 h')
        self.assertEqual(jan['AG11'].value, 22, 'working days of January 2024 (New Year excluded)')
        self.assertEqual(jan['D14'].value, 1, 'daily column total')
        syn = wb['Synthèse %d' % YEAR]
        self.assertEqual(syn['D12'].value, 1.5)
        self.assertEqual(syn['F12'].value, 0.25)
        self.assertEqual(syn['P12'].value, 1.75)
        self.assertEqual(syn['P13'].value, 1.5)
        self.assertEqual(syn['F11'].value, 1, 'absence in March')
        self.assertEqual(syn['P14'].value, 3.25, 'total without absences')
        self.assertEqual(syn['F14'].value, 0.25)

    def test_cutoff_month(self):
        archive, _filename = self._generate(month=1)
        self.assertEqual(sorted(archive.namelist()), [JEAN_FILE], 'Paul only has timesheets in February')
        if openpyxl is not None:
            wb = self._open(archive, JEAN_FILE, data_only=True)
            syn = wb['Synthèse %d' % YEAR]
            self.assertEqual(syn['B13'].value, 'TOTAL', 'no absence row: 2 project rows then the total')
            self.assertEqual(syn['P13'].value, 2)
            self.assertIsNone(wb['Février']['P18'].value)

    def test_wizard(self):
        wizard = self.env['hr.timesheet.cir.export.wizard'].with_user(self.manager).create({
            'year': str(YEAR), 'month': '3', 'employee_ids': [(6, 0, self.employees.ids)],
        })
        self.assertEqual((wizard.date_from, wizard.date_to), (date(YEAR, 1, 1), date(YEAR, 3, 31)))
        self.assertIn(self.task_leave, wizard.absence_task_ids)
        action = wizard.action_export()
        self.assertEqual(action['type'], 'ir.actions.act_url')
        self.assertEqual(action['target'], 'download')
        self.assertIn('/web/content/hr.timesheet.cir.export.wizard/%d/zip_file/' % wizard.id, action['url'])
        self.assertEqual(wizard.zip_filename, 'Fiche_de_temps_%d.zip' % YEAR)
        self.assertTrue(wizard.zip_file)
        defaults = self.env['hr.timesheet.cir.export.wizard'].with_user(self.manager).default_get(['year', 'month'])
        year, month = self.env['hr.timesheet.cir.export']._default_period()
        self.assertEqual((defaults['year'], defaults['month']), (str(year), str(month)))


@tagged('post_install', '-at_install')
class TestCirExportController(HttpCase, TestCirExportCommon):

    def test_download_route(self):
        self.authenticate('cir_admin', 'cir_admin_pwd_123')
        response = self.url_open('/hr_timesheet_cir_export/download', data={
            'year': str(YEAR), 'month': '3', 'csrf_token': http.Request.csrf_token(self),
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers['Content-Type'], 'application/zip')
        self.assertIn('Fiche_de_temps_%d.zip' % YEAR, response.headers['Content-Disposition'])
        archive = zipfile.ZipFile(io.BytesIO(response.content))
        self.assertIn(JEAN_FILE, archive.namelist())

        response = self.url_open('/hr_timesheet_cir_export/download', data={
            'year': 'abc', 'csrf_token': http.Request.csrf_token(self),
        })
        self.assertEqual(response.status_code, 400)

    def test_download_route_forbidden(self):
        self.authenticate('cir_user', 'cir_user_pwd_123')
        response = self.url_open('/hr_timesheet_cir_export/download', data={
            'csrf_token': http.Request.csrf_token(self),
        })
        self.assertEqual(response.status_code, 403)
