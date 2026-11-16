# -*- coding: utf-8 -*-
from odoo import Command, _, models
from odoo.exceptions import UserError
from odoo.tools import float_is_zero
from odoo.tools.misc import formatLang

VENDOR_TYPES = ('in_invoice', 'in_refund')
AMOUNT_TOLERANCE = 0.02


class AccountMove(models.Model):
    _name = 'account.move'
    _inherit = ['account.move', 'local.ai.document.mixin']

    def _local_ai_check_readable(self):
        self.ensure_one()
        if self.move_type not in VENDOR_TYPES or self.state != 'draft':
            raise UserError(_("Only draft vendor bills and refunds can be read by the AI."))

    def _local_ai_is_blank(self):
        return not self.invoice_line_ids

    def _extend_with_attachments(self, files_data, new=False):
        # Bill created from a document (upload, email) without electronic
        # invoice inside: read by the AI in the background.
        res = super()._extend_with_attachments(files_data, new=new)
        self._local_ai_enqueue_new_documents()
        return res

    def _local_ai_apply(self, values):
        self.ensure_one()
        filled, kept, warnings = [], [], []
        blank = self._local_ai_is_blank()
        vals = {}

        def propose(field_name, value, empty):
            is_record = isinstance(value, models.BaseModel)
            nothing_read = not value if is_record else value in (None, '')
            if nothing_read:
                return
            if empty:
                vals[field_name] = value.id if is_record else value
                filled.append(self._local_ai_label(field_name))
            elif self[field_name] != value:
                kept.append(self._local_ai_label(field_name))

        propose('partner_id', values['partner'], not self.partner_id)
        propose('ref', values['reference'], not self.ref)
        propose('invoice_date', values['date'], not self.invoice_date)
        currency = values['currency']
        if currency and currency != self.currency_id:
            if not currency.active:
                warnings.append(_("The currency %s of the document is not active in Odoo.", currency.name))
            else:
                propose('currency_id', currency, blank)
        if vals:
            self.write(vals)

        # without payment term, the due date is the one of the document
        if values['date_due'] and not self.invoice_payment_term_id and values['date_due'] != self.invoice_date_due:
            if blank:
                self.invoice_date_due = values['date_due']
                filled.append(self._local_ai_label('invoice_date_due'))
            else:
                kept.append(self._local_ai_label('invoice_date_due'))

        if blank and values['total'] is not None:
            warnings += self._local_ai_add_line(values)
            filled.append(_("invoice line"))
        if values['total'] is not None and abs(self.amount_total - values['total']) > AMOUNT_TOLERANCE:
            warnings.append(_(
                "The total of the document (%(read)s) differs from the total of the bill (%(bill)s): "
                "check the amounts and the taxes.",
                read=formatLang(self.env, values['total'], currency_obj=self.currency_id),
                bill=formatLang(self.env, self.amount_total, currency_obj=self.currency_id)))
        return filled, kept, warnings

    def _local_ai_add_line(self, values):
        """One line at the untaxed amount, with the purchase tax matching the
        taxes read; at the total, without tax, when the taxes were not read."""
        warnings = []
        description = values['description'] or values['partner_name'] or _("Read by the AI")
        with_taxes = values['consistent']
        price = values['untaxed'] if with_taxes else values['total']
        self.write({'invoice_line_ids': [Command.create({'name': description, 'quantity': 1, 'price_unit': price})]})
        line = self.invoice_line_ids[-1:]
        if not with_taxes:
            line.tax_ids = [Command.clear()]
            warnings.append(_("The untaxed amount and the taxes were not read: the line holds the total without "
                              "tax, check it."))
        elif float_is_zero(values['tax'], precision_digits=2):
            line.tax_ids = [Command.clear()]
        elif not self._local_ai_taxes_match(line.tax_ids, values):
            taxes = self._local_ai_find_taxes(values)
            if taxes:
                line.tax_ids = [Command.set(taxes.ids)]
                warnings.append(_("Tax chosen from the amounts read: %s, check it.",
                                  ', '.join(taxes.mapped('display_name'))))
            else:
                warnings.append(_(
                    "No purchase tax matches the taxes of the document (%(tax)s on %(untaxed)s): check the taxes.",
                    tax=formatLang(self.env, values['tax'], currency_obj=self.currency_id),
                    untaxed=formatLang(self.env, values['untaxed'], currency_obj=self.currency_id)))
        return warnings

    def _local_ai_taxes_match(self, taxes, values):
        if not taxes or any(tax.amount_type != 'percent' or tax.price_include for tax in taxes):
            return False
        expected = round(values['untaxed'] * sum(taxes.mapped('amount')) / 100, 2)
        return abs(expected - values['tax']) <= AMOUNT_TOLERANCE

    def _local_ai_find_taxes(self, values):
        """Purchase tax, without reverse charge, that gives the taxes read on
        the untaxed amount read; the default purchase tax of the company is
        preferred, then the taxes of the same scope."""
        Tax = self.env['account.tax']
        candidates = Tax.search([
            *Tax._check_company_domain(self.company_id),
            ('type_tax_use', '=', 'purchase'), ('amount_type', '=', 'percent'), ('amount', '>', 0),
        ]).filtered(lambda tax: not tax.price_include
                    and not any(line.factor_percent < 0 for line in tax.invoice_repartition_line_ids)
                    and self._local_ai_taxes_match(tax, values))
        if not candidates:
            return Tax
        default = self.company_id.account_purchase_tax_id
        tax = (candidates & default) or candidates.filtered(lambda tax: tax.tax_scope == default.tax_scope) or candidates
        tax = tax.sorted(lambda tax: (tax.sequence, tax.id))[:1]
        return self.fiscal_position_id.map_tax(tax) if self.fiscal_position_id else tax
