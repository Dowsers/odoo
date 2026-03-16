# -*- coding: utf-8 -*-
{
    'name': 'Employee Appraisal Management',
    'version': '19.0.1.0.0',
    'category': 'Human Resources',
    'summary': 'Manage employee appraisals and performance reviews',
    'description': """
Employee Appraisal Management
=============================
This module allows you to:
* Create and manage employee appraisals
* Define appraisal templates with customizable criteria
* Schedule periodic appraisals for employees
* Track appraisal history
* Generate appraisal reports

Features:
---------
* Appraisal forms with rating scales
* Self-assessment and manager assessment
* Goal setting and tracking
* Feedback and comments
* Email notifications
* Appraisal calendar view
    """,
    'author': 'Custom Development',
    'website': '',
    'license': 'LGPL-3',
    'depends': ['hr', 'mail', 'calendar'],
    'data': [
        'security/ir.model.access.csv',
        'views/hr_appraisal_custom_views.xml',
        'views/hr_appraisal_template_views.xml',
        'views/hr_employee_views.xml',
        'views/menus.xml',
        'wizard/hr_appraisal_request_wizard_views.xml',
        'data/ir_cron.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
