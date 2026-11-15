# -*- coding: utf-8 -*-
{
    'name': 'Local Instance - No Links to odoo.com',
    'version': '19.0.1.0.0',
    'category': 'Hidden/Tools',
    'summary': 'Remove the links to odoo.com and the calls to Odoo online services',
    'description': """
Local Instance - No Links to odoo.com
=====================================
For an Odoo instance used on a private network only:

* no "My Odoo.com account", "Documentation" and "Support" entries in the
  user menu, no redirection to accounts.odoo.com;
* no "Powered by Odoo" links on the login page, the portal and the
  e-mails (notification layouts, digest, templates);
* no Enterprise upsell: settings shown with an "Upgrade" dialog, modules
  to buy in Apps, "Third-Party Apps" and "Theme Store" menus;
* no In-App Purchase block in the settings;
* the editor does not call Odoo's online services (ChatGPT translation,
  illustrations library);
* the "Publisher: Update Notification" telemetry is deactivated and
  neutralised.
    """,
    'author': 'Custom Development',
    'website': '',
    'license': 'LGPL-3',
    'depends': ['web', 'mail', 'base_setup', 'iap', 'html_editor', 'portal', 'digest', 'hr_expense'],
    'data': [
        'data/data.xml',
        'views/templates.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'web_local_only/static/src/user_menu.js',
            'web_local_only/static/src/editor.js',
            'web_local_only/static/src/local_only.scss',
            'web_local_only/static/src/templates.xml',
        ],
    },
    'post_init_hook': 'post_init_hook',
    'installable': True,
    'application': False,
    'auto_install': False,
}
