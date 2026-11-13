# -*- coding: utf-8 -*-
{
    'name': 'Timesheets - CIR Export (ZIP)',
    'version': '19.0.1.0.0',
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
per day) and the public holidays.

Times entered in hours in Odoo are converted to days with the working
hours per day of the employee's working schedule.
    """,
    'author': 'Custom Development',
    'website': '',
    'license': 'LGPL-3',
    'depends': ['hr_timesheet'],
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
