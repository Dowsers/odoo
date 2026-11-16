# -*- coding: utf-8 -*-
{
    'name': 'Bills and Receipts - Reading by the Local AI',
    'version': '19.0.1.0.0',
    'category': 'Accounting',
    'summary': 'The local AI reads vendor bills and expense receipts (PDF or picture) and fills the draft',
    'description': """
Bills and Receipts - Reading by the Local AI
============================================
The local AI server (local_ai) reads the document attached to a draft vendor
bill or to a draft expense and fills the fields that are still empty: vendor
(searched among the existing contacts, never created), reference, dates,
currency, amount and taxes. The values read are written in the chatter, with
what was filled and what was left as is, to be checked before validation.

* automatically, in the background, when a bill or an expense is created by
  uploading its document (Upload button, email to the journal alias), when
  no electronic invoice (Factur-X, UBL) was found in it;
* on demand, with the "Read the document (AI)" button of the draft.

PDF with text are read as text; pictures and scanned PDF by the vision of
the model (pdftoppm of poppler-utils renders the scanned pages). The
documents never leave the company network.
    """,
    'author': 'Custom Development',
    'website': '',
    'license': 'LGPL-3',
    'depends': ['local_ai', 'account', 'hr_expense'],
    'data': [
        'views/account_move_views.xml',
        'views/hr_expense_views.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
