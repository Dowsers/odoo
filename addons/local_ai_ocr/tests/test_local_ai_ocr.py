# -*- coding: utf-8 -*-
import base64
import io
import json
from datetime import date
from unittest.mock import patch

from PIL import Image, ImageDraw

from odoo import Command
from odoo.exceptions import UserError
from odoo.tests import tagged

from odoo.addons.hr_expense.tests.common import TestExpenseCommon
from odoo.addons.local_ai.tests.common import configure, fake_ollama
from odoo.addons.local_ai_ocr.models.local_ai_document import MAX_SIDE, parse_amount, parse_date

DOCUMENT_PATH = 'odoo.addons.local_ai_ocr.models.local_ai_document'


def text_pdf(lines):
    from reportlab.pdfgen import canvas
    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer)
    for index, line in enumerate(lines):
        pdf.drawString(50, 800 - 20 * index, line)
    pdf.showPage()
    pdf.save()
    return buffer.getvalue()


def picture(size=(600, 800), image_format='PNG', text="TICKET 36,30 EUR"):
    image = Image.new('RGB', size, 'white')
    ImageDraw.Draw(image).text((40, 40), text, fill='black')
    buffer = io.BytesIO()
    image.save(buffer, format=image_format)
    return buffer.getvalue()


INVOICE_LINES = [
    "Imprimerie Test SARL - 12 rue des Essais, 75000 Paris",
    "FACTURE F-2026-042 du 15/03/2026, payable le 14/04/2026",
    "Impression de 500 plaquettes commerciales, format A5, recto verso, papier couché 170 g",
    "Total HT : 100,00 EUR - TVA 20 % : 20,00 EUR - Total TTC : 120,00 EUR",
]


@tagged('post_install', '-at_install')
class TestLocalAIOcr(TestExpenseCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        configure(cls.env)
        cls.company = cls.company_data['company']
        cls.currency = cls.company_data['currency']
        cls.vendor = cls.env['res.partner'].create({'name': 'Imprimerie Test SARL', 'company_id': False})
        cls.restaurant = cls.env['res.partner'].create({'name': 'Restaurant Le Test', 'company_id': False})
        Tax = cls.env['account.tax']

        def distribution(factors):
            return [Command.create({'repartition_type': 'base'})] + [
                Command.create({'repartition_type': 'tax', 'factor_percent': factor}) for factor in factors]

        # a reverse charge tax at the same rate must never be chosen
        cls.tax_reverse_20 = Tax.create({
            'name': 'VAT 20% reverse charge', 'amount': 20, 'type_tax_use': 'purchase', 'sequence': 1,
            'company_id': cls.company.id,
            'invoice_repartition_line_ids': distribution([100, -100]),
            'refund_repartition_line_ids': distribution([100, -100]),
        })
        cls.tax_20 = Tax.create({'name': 'VAT 20% purchases', 'amount': 20, 'type_tax_use': 'purchase',
                                 'sequence': 5, 'company_id': cls.company.id})

    def answer(self, **values):
        data = {
            'fournisseur': 'Imprimerie Test', 'tva_fournisseur': None, 'numero': 'F-2026-042',
            'date': '15/03/2026', 'echeance': '2026-04-14', 'devise': self.currency.name,
            'montant_ht': '100,00', 'montant_tva': 20, 'montant_ttc': '120.00', 'description': 'Impression de plaquettes',
        }
        data.update(values)
        return json.dumps(data)

    def attach(self, record, raw, name):
        return self.env['ir.attachment'].create({'name': name, 'raw': raw, 'res_model': record._name, 'res_id': record.id})

    def new_bill(self, move_type='in_invoice'):
        return self.env['account.move'].create({'move_type': move_type, 'company_id': self.company.id})

    def last_note(self, record):
        return str(record.message_ids.filtered(lambda message: message.subtype_id == self.env.ref('mail.mt_note'))[:1].body)

    def process_queue(self, answers):
        with fake_ollama(answers) as calls, \
                patch.object(self.registry['ir.cron'], '_commit_progress', return_value=600):
            self.env['local.ai']._cron_process_queue()
        return calls

    # ------------------------------------------------------------------
    def test_parsing(self):
        for value, expected in [
            ("1 234,56 €", 1234.56), ("1,234.56", 1234.56), ("12,5", 12.5), ("1.234.567", 1234567.0),
            ("-45.10", 45.1), (12, 12.0), ("abc", None), (True, None), (None, None), ("1,234", 1234.0),
        ]:
            self.assertEqual(parse_amount(value), expected, value)
        today = date(2026, 11, 16)
        for value, expected in [
            ("2026-03-15", date(2026, 3, 15)), ("15/03/2026", date(2026, 3, 15)), ("15.03.26", date(2026, 3, 15)),
            ("le 5/3/2026", date(2026, 3, 5)), ("31/02/2026", None), ("1999-01-01", None), ("2040-01-01", None),
            (None, None), ("null", None),
        ]:
            self.assertEqual(parse_date(value, today), expected, value)

        Document = self.env['local.ai.document']
        values = Document._normalize({'montant_ht': 100, 'montant_tva': None, 'montant_ttc': 120, 'devise': '€',
                                      'tva_fournisseur': 'fr 12 345 678 901', 'fournisseur': {'nom': 'ACME'},
                                      'date': '2026-03-15', 'echeance': '2026-03-01'})
        self.assertEqual((values['untaxed'], values['tax'], values['total']), (100.0, 20.0, 120.0))
        self.assertTrue(values['consistent'])
        self.assertEqual(values['currency_code'], 'EUR')
        self.assertEqual(values['currency'].name, 'EUR')
        self.assertEqual(values['vat'], 'FR12345678901')
        self.assertEqual(values['partner_name'], 'ACME')
        self.assertFalse(values['date_due'], "a due date before the date is dropped")
        swapped = Document._normalize({'montant_ht': 120, 'montant_tva': 20, 'montant_ttc': 100})
        self.assertEqual((swapped['untaxed'], swapped['tax'], swapped['total']), (None, None, 100.0))
        self.assertFalse(swapped['consistent'])
        wrong = Document._normalize({'montant_ht': 100, 'montant_tva': 30, 'montant_ttc': 120, 'devise': 'XX',
                                     'tva_fournisseur': 'inconnu', 'fournisseur': 'null'})
        self.assertFalse(wrong['consistent'])
        self.assertFalse(wrong['currency'] or wrong['vat'] or wrong['partner_name'])

    def test_document_content(self):
        Document = self.env['local.ai.document']
        bill = self.new_bill()
        content = Document._document_content(self.attach(bill, text_pdf(INVOICE_LINES), 'facture.pdf'))
        self.assertIn('F-2026-042', content['text'])

        content = Document._document_content(self.attach(bill, picture((3000, 2000)), 'ticket.png'))
        self.assertEqual(len(content['images']), 1)
        image = Image.open(io.BytesIO(base64.b64decode(content['images'][0])))
        self.assertEqual((image.format, max(image.size)), ('JPEG', MAX_SIDE))

        scan = io.BytesIO()
        Image.open(io.BytesIO(picture())).save(scan, format='PDF')
        attachment = self.attach(bill, scan.getvalue(), 'scan.pdf')
        self.assertEqual(len(Document._document_content(attachment)['images']), 1)
        with patch(DOCUMENT_PATH + '.shutil.which', return_value=None):
            self.assertEqual(len(Document._document_content(attachment)['images']), 1, "embedded scan picture")

        with self.assertRaises(UserError):
            Document._document_content(self.attach(bill, b'not a document', 'notes.txt'))
        with self.assertRaises(UserError):
            Document._document_content(self.attach(bill, b'%PDF-1.4 broken', 'broken.pdf'))

    def test_bill(self):
        bill = self.new_bill()
        self.assertTrue(bill.local_ai_enabled)
        with fake_ollama([]), self.assertRaisesRegex(UserError, "Attach"):
            bill.action_local_ai_read_document()
        self.attach(bill, text_pdf(INVOICE_LINES), 'facture.pdf')
        with fake_ollama([self.answer()]) as calls:
            bill.action_local_ai_read_document()
        self.assertEqual(calls[0]['format'], 'json')
        self.assertEqual(calls[0]['options']['temperature'], 0)
        self.assertIn('F-2026-042', calls[0]['messages'][-1]['content'])
        self.assertNotIn('images', calls[0]['messages'][-1])
        self.assertEqual(bill.partner_id, self.vendor)
        self.assertEqual(bill.ref, 'F-2026-042')
        self.assertEqual(bill.invoice_date, date(2026, 3, 15))
        self.assertEqual(bill.invoice_date_due, date(2026, 4, 14))
        self.assertEqual(len(bill.invoice_line_ids), 1)
        self.assertEqual(bill.invoice_line_ids.name, 'Impression de plaquettes')
        self.assertEqual(bill.invoice_line_ids.price_unit, 100)
        self.assertEqual(bill.invoice_line_ids.tax_ids, self.tax_20)
        self.assertEqual(bill.amount_total, 120)
        self.assertEqual(bill.ai_state, 'done')
        note = self.last_note(bill)
        self.assertIn('facture.pdf', note)
        self.assertIn('F-2026-042', note)

        # a bill already filled: nothing is changed, the differences are reported
        with fake_ollama([self.answer(numero='F-2026-043', montant_ttc=130)]):
            bill.action_local_ai_read_document()
        self.assertEqual(bill.ref, 'F-2026-042')
        self.assertEqual(len(bill.invoice_line_ids), 1)
        self.assertIn('130', self.last_note(bill))

        bill.action_post()
        with fake_ollama([]) as calls, self.assertRaises(UserError):
            bill.action_local_ai_read_document()
        self.assertFalse(calls)
        invoice = self.new_bill('out_invoice')
        with self.assertRaises(UserError):
            invoice.action_local_ai_read_document()

    def test_bill_without_taxes_read(self):
        bill = self.new_bill()
        self.attach(bill, text_pdf(INVOICE_LINES), 'facture.pdf')
        answer = self.answer(fournisseur=self.company.name, montant_ht=None, montant_tva=None, numero=None)
        with fake_ollama([answer]):
            bill.action_local_ai_read_document()
        self.assertFalse(bill.partner_id, "our own company is never taken for the vendor")
        self.assertEqual(bill.invoice_line_ids.price_unit, 120)
        self.assertFalse(bill.invoice_line_ids.tax_ids)
        self.assertEqual(bill.amount_total, 120)

    def test_bill_from_upload(self):
        Move = self.env['account.move'].with_context(default_move_type='in_invoice')
        attachment = self.env['ir.attachment'].create({'name': 'scan.png', 'raw': picture()})
        bill = Move._create_records_from_attachments(attachment)
        self.assertEqual(bill.ai_state, 'queued')
        calls = self.process_queue([self.answer()])
        self.assertEqual(len(calls[0]['messages'][-1]['images']), 1)
        self.assertEqual(bill.ai_state, 'done')
        self.assertEqual(bill.amount_total, 120)
        self.assertIn('scan.png', self.last_note(bill))

        # unreadable answer: the error is kept on the bill
        bill = Move._create_records_from_attachments(self.env['ir.attachment'].create({'name': 'b.png', 'raw': picture()}))
        self.process_queue(['not json'])
        self.assertEqual(bill.ai_state, 'error')
        self.assertTrue(bill.ai_error)
        self.assertFalse(bill.invoice_line_ids)

        # local AI not configured: nothing is queued
        self.env['ir.config_parameter'].sudo().set_param('local_ai.url', False)
        bill = Move._create_records_from_attachments(self.env['ir.attachment'].create({'name': 'c.png', 'raw': picture()}))
        self.assertFalse(bill.ai_state)
        self.assertFalse(bill.local_ai_enabled)

    def test_expense(self):
        Expense = self.env['hr.expense'].with_user(self.expense_user_employee)
        attachment = self.env['ir.attachment'].with_user(self.expense_user_employee).create({
            'name': 'ticket.jpg', 'raw': picture(image_format='JPEG'), 'res_model': 'hr.expense', 'res_id': 0})
        expense = Expense.browse(Expense.create_expense_from_attachments(attachment.ids))
        self.assertEqual(expense.ai_state, 'queued')
        answer = self.answer(fournisseur='Restaurant Le Test', numero=None, description='Repas client',
                             montant_ht=None, montant_tva=None, montant_ttc='36,30')
        calls = self.process_queue([answer])
        self.assertTrue(calls[0]['messages'][-1]['images'])
        self.assertEqual(expense.ai_state, 'done')
        self.assertEqual(expense.name, 'Repas client')
        self.assertEqual(expense.date, date(2026, 3, 15))
        self.assertEqual(expense.total_amount_currency, 36.30)
        self.assertEqual(expense.vendor_id, self.restaurant)
        self.assertIn('ticket.jpg', self.last_note(expense))

        # read again by the employee: the total entered is kept
        with fake_ollama([answer.replace('36,30', '40')]):
            expense.action_local_ai_read_document()
        self.assertEqual(expense.total_amount_currency, 36.30)

        expense.sudo().action_submit()
        with fake_ollama([]), self.assertRaises(UserError):
            expense.action_local_ai_read_document()
