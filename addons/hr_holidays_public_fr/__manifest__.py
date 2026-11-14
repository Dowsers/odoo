# -*- coding: utf-8 -*-
{
    'name': 'Time Off - French Public Holidays',
    'version': '19.0.1.0.0',
    'category': 'Human Resources/Time Off',
    'summary': 'Import the official French public holidays from calendrier.api.gouv.fr',
    'description': """
Time Off - French Public Holidays
=================================
Imports the official French public holidays, published by the government on
https://calendrier.api.gouv.fr (API "Jours fériés" of api.gouv.fr), into the
public holidays of Odoo (Time Off > Configuration > Public Holidays):

* every week (scheduled action), on demand (button in the public holidays
  list and in the settings), and when the settings change;
* for the current and the next year, for every company with a zone
  (metropolitan France, Alsace-Moselle or an overseas territory, set from the
  company's country);
* Whit Monday is left out while it is a worked day (journée de solidarité,
  setting shared with hr_timesheet_consistency);
* a public holiday recorded by hand is never changed, and a public holiday
  deleted in Odoo is not imported again; an upcoming public holiday that
  the government no longer publishes is removed;
* the past is never rewritten: no past public holiday is removed and no
  timesheet is generated for the public holidays already past.

For the imported years, the timesheet consistency checks and the CIR export
follow the public holidays of Odoo instead of the computed French public
holidays.
    """,
    'author': 'Custom Development',
    'website': '',
    'license': 'LGPL-3',
    'depends': ['hr_holidays', 'project_timesheet_holidays', 'hr_timesheet_consistency'],
    'external_dependencies': {'python': ['requests']},
    'data': [
        'security/ir.model.access.csv',
        'security/hr_public_holiday_fr_security.xml',
        'data/ir_cron.xml',
        'views/hr_public_holiday_fr_views.xml',
        'views/resource_calendar_leaves_views.xml',
        'views/res_config_settings_views.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
