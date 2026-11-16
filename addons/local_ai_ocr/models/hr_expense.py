# -*- coding: utf-8 -*-
from odoo import _, models
from odoo.exceptions import UserError
from odoo.tools import float_is_zero


class HrExpense(models.Model):
    _name = 'hr.expense'
    _inherit = ['hr.expense', 'local.ai.document.mixin']

    def _local_ai_check_readable(self):
        self.ensure_one()
        if self.state != 'draft':
            raise UserError(_("Only draft expenses can be read by the AI."))
        if not self.env.su and not self.is_editable:
            raise UserError(_("You cannot edit this expense."))

    def _local_ai_is_blank(self):
        return float_is_zero(self.total_amount_currency, precision_rounding=self.currency_id.rounding or 0.01)

    def create_expense_from_attachments(self, attachment_ids=None, view_type='list'):
        # Expenses created from uploaded receipts: read by the AI in the background.
        expense_ids = super().create_expense_from_attachments(attachment_ids=attachment_ids, view_type=view_type)
        if isinstance(expense_ids, list):
            self.browse(expense_ids)._local_ai_enqueue_new_documents()
        return expense_ids

    def _local_ai_apply(self, values):
        """A blank expense takes the description, date, currency and total
        of the receipt; otherwise only an empty vendor is filled."""
        self.ensure_one()
        filled, kept, warnings = [], [], []
        blank = self._local_ai_is_blank()
        vals = {}

        def propose(field_name, value, empty):
            if not value:
                return
            if empty:
                vals[field_name] = value.id if isinstance(value, models.BaseModel) else value
                filled.append(self._local_ai_label(field_name))
            elif self[field_name] != value:
                kept.append(self._local_ai_label(field_name))

        propose('vendor_id', values['partner'], not self.vendor_id)
        propose('name', values['description'] or values['partner_name'], blank)
        propose('date', values['date'], blank)
        currency = values['currency']
        if currency and currency != self.currency_id:
            if currency.active:
                propose('currency_id', currency, blank)
            else:
                warnings.append(_("The currency %s of the receipt is not active in Odoo.", currency.name))
        if values['total'] is not None:
            if self.product_has_cost:
                warnings.append(_("The category of the expense has a fixed cost: the total of the receipt "
                                  "was not entered."))
            elif blank:
                vals['total_amount_currency'] = values['total']
                filled.append(self._local_ai_label('total_amount_currency'))
            elif abs(self.total_amount_currency - values['total']) > 0.02:
                kept.append(self._local_ai_label('total_amount_currency'))
        if vals:
            self.write(vals)
        return filled, kept, warnings
