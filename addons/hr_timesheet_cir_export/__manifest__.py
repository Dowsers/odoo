# -*- coding: utf-8 -*-
{
    'name': 'Timesheets - CIR Export (ZIP)',
    'version': '19.0.1.1.0',
    'category': 'Services/Timesheets',
    'summary': 'Download a ZIP with one yearly CIR activity report (xlsx) per employee',
    'description': """
Timesheets - CIR Export (ZIP)
=============================
Adds, for timesheet administrators, a download button on the
"All Timesheets" action (/odoo/all-timesheets, every view type) and a
menu entry Timesheets > Timesheets > CIR Export (ZIP).

The ZIP contains, for the current year stopped at the previous complete
month, one workbook per employee laid out like the
"Rapport mensuel d'activité - CIR" template: a yearly synthesis sheet,
a ReadMe sheet, one sheet per month (days spent per project / task and
per day), the public holidays and a "Contrôles" sheet listing the
inconsistencies to correct in Odoo. The ZIP also holds a summary of the
inconsistencies of all employees.

Times are converted to days with the length of one day (the day of the
timesheet encoding unit, or of the working schedule when timesheets are
encoded in hours). Weekends and public holidays are not
working days: absences logged on them are left out, activities logged on
them are flagged, like the dates holding more than one day.
    """,
    'author': 'Custom Development',
    'website': '',
    'license': 'LGPL-3',
    'depends': ['hr_timesheet', 'hr_timesheet_consistency'],
    'external_dependencies': {'python': ['xlsxwriter']},
    'data': [
        'security/ir.model.access.csv',
        'wizard/timesheet_cir_export_wizard_views.xml',
        'views/menus.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'hr_timesheet_cir_export/static/src/**/*',
        ],
    },
    'installable': True,
    'application': False,
    'auto_install': False,
}
