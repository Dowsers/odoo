# -*- coding: utf-8 -*-
{
    'name': 'Appraisals - AI Summary (Local AI)',
    'version': '19.0.1.0.0',
    'category': 'Human Resources',
    'summary': 'Summary of an appraisal written by the local AI, without sending HR data outside',
    'description': """
Appraisals - AI Summary (Local AI)
==================================
"AI Summary" button on the appraisals (hr_appraisal_custom): the local AI
server (local_ai) writes a summary of the appraisal (overview, strengths,
areas for improvement, objectives to follow) from its criteria, objectives,
competencies and comments. The HR data never leave the company network.
Remuneration notes are not sent to the AI.
    """,
    'author': 'Custom Development',
    'website': '',
    'license': 'LGPL-3',
    'depends': ['local_ai', 'hr_appraisal_custom'],
    'data': [
        'views/hr_appraisal_custom_views.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
