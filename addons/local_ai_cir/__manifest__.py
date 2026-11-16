# -*- coding: utf-8 -*-
{
    'name': 'Timesheets - CIR Assistant (Local AI)',
    'version': '19.0.1.0.0',
    'category': 'Services/Timesheets',
    'summary': 'Timesheet descriptions to complete for the CIR, and drafts of the CIR dossier, by the local AI',
    'description': """
Timesheets - CIR Assistant (Local AI)
=====================================
Uses the local AI server (local_ai) on the timesheets, without sending any
data outside the company network:

* "Descriptions to Complete (CIR)": the timesheets of activities whose
  description is missing ("/") or too short to justify the time for the
  Crédit d'Impôt Recherche. The local AI suggests a description from the
  task and the descriptions already written; the employee edits it or
  applies it.
* "CIR Dossier (AI Drafts)": for each R&D task of a year, a draft of the
  technical description (objectives, scientific and technical obstacles,
  work carried out, results) written from the timesheets, plus the facts
  computed by Odoo (period, days, people), printable as PDF. Sections
  without information are marked "À compléter" instead of being invented.
    """,
    'author': 'Custom Development',
    'website': '',
    'license': 'LGPL-3',
    'depends': ['local_ai', 'hr_timesheet', 'hr_timesheet_consistency'],
    'data': [
        'security/ir.model.access.csv',
        'views/account_analytic_line_views.xml',
        'wizard/cir_draft_wizard_views.xml',
        'views/cir_draft_views.xml',
        'report/cir_draft_report.xml',
        'views/menus.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
