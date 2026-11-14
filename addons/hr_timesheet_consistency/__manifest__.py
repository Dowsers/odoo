# -*- coding: utf-8 -*-
{
    'name': 'Timesheets - Consistency Checks',
    'version': '19.0.1.1.0',
    'category': 'Services/Timesheets',
    'summary': 'At most one day of activity per calendar day, no activity on public holidays',
    'description': """
Timesheets - Consistency Checks
===============================
Checks run whenever a timesheet is created or modified:

* an employee cannot log more than one day on a calendar day, absences
  included (one day = the day of the timesheet encoding unit, or the hours
  per day of the working schedule when timesheets are encoded in hours);
* no activity can be logged on a public holiday (French public holidays and
  the public holidays recorded in Odoo). Absences remain allowed, and
  timesheet administrators can log exceptional work for other employees.

Only what an operation makes worse is refused: inconsistent lines entered
before the installation can still be corrected, and the timesheets that
Odoo generates for time off and public holidays are never refused.

A task flag "Absence (timesheets)" tells absences from activities. The
module also provides the rules shared with the CIR export
(hr_timesheet_cir_export): public holidays, absence tasks and length of
a day. Whit Monday is a worked day by default (system parameter
hr_timesheet_consistency.whit_monday_worked).
    """,
    'author': 'Custom Development',
    'website': '',
    'license': 'LGPL-3',
    'depends': ['hr_timesheet'],
    'data': [
        'data/ir_config_parameter.xml',
        'views/project_task_views.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
