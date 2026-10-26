# -*- coding: utf-8 -*-
{
    'name': 'Timesheets - Calendar Default View',
    'version': '19.0.1.0.0',
    'category': 'Services/Timesheets',
    'summary': 'Open My Timesheets in calendar view by default',
    'description': """
Timesheets - Calendar Default View
==================================
Makes the calendar the default view of the "My Timesheets" action
(/odoo/timesheets) on desktop. Small screens keep the kanban view
(mobile_view_mode).

The list, form, kanban, pivot and graph views remain available
from the view switcher.
    """,
    'author': 'Custom Development',
    'website': '',
    'license': 'LGPL-3',
    'depends': ['hr_timesheet'],
    'data': [
        'views/hr_timesheet_views.xml',
    ],
    'uninstall_hook': 'uninstall_hook',
    'installable': True,
    'application': False,
    'auto_install': False,
}
