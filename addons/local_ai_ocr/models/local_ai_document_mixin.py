# -*- coding: utf-8 -*-
from markupsafe import Markup

from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools.misc import format_date, formatLang

from .local_ai_document import READABLE_MIMETYPES


class LocalAIDocumentMixin(models.AbstractModel):
    """Records filled from their document (vendor bill, expense) by the
    local AI: on demand (action_local_ai_read_document) or in the background
    (local.ai.queue.mixin)."""
    _name = 'local.ai.document.mixin'
    _inherit = ['local.ai.queue.mixin']
    _description = 'Record read from its document by the local AI'

    local_ai_enabled = fields.Boolean(compute='_compute_local_ai_enabled')

    @api.depends_context('uid')
    def _compute_local_ai_enabled(self):
        enabled = self.env['local.ai']._is_enabled()
        for record in self:
            record.local_ai_enabled = enabled

    # ------------------------------------------------------------------
    # To implement
    # ------------------------------------------------------------------
    def _local_ai_check_readable(self):
        """Raise a UserError if the record cannot be filled by the AI."""
        raise NotImplementedError()

    def _local_ai_is_blank(self):
        """True while nothing was entered on the record but its document."""
        raise NotImplementedError()

    def _local_ai_apply(self, values):
        """Fill the record with the values read; return (filled, kept,
        warnings): labels of the fields filled, of the fields left as they
        were, and messages for the user."""
        raise NotImplementedError()

    # ------------------------------------------------------------------
    # Common
    # ------------------------------------------------------------------
    def _local_ai_attachment(self):
        """Document of the record: its main attachment, else its last PDF or
        picture."""
        self.ensure_one()
        attachment = self.message_main_attachment_id
        if attachment and attachment.mimetype in READABLE_MIMETYPES:
            return attachment
        return self.env['ir.attachment'].search([
            ('res_model', '=', self._name), ('res_id', '=', self.id), ('mimetype', 'in', READABLE_MIMETYPES),
        ], order='id desc', limit=1)

    def _local_ai_can_read(self):
        try:
            self._local_ai_check_readable()
        except UserError:
            return False
        return True

    def _local_ai_enqueue_new_documents(self):
        """Queue the blank records holding a document, when the AI is set."""
        if not self or not self.env['local.ai']._is_enabled():
            return
        self.filtered(lambda record: record.ai_state != 'queued' and record._local_ai_can_read()
                      and record._local_ai_is_blank() and record._local_ai_attachment())._local_ai_enqueue()

    def _local_ai_label(self, field_name):
        return self._fields[field_name]._description_string(self.env)

    def _local_ai_find_partner(self, values):
        if not (values.get('partner_name') or values.get('vat')):
            return self.env['res.partner']
        partner = self.env['res.partner']._retrieve_partner(
            name=values.get('partner_name'), vat=values.get('vat'), company=self.company_id)
        # the model may take the customer (our company) for the vendor
        return partner if partner.commercial_partner_id != self.company_id.partner_id else partner.browse()

    def _local_ai_read(self):
        """Read the document and fill the record; return the values read."""
        self.ensure_one()
        self._local_ai_check_readable()
        attachment = self._local_ai_attachment()
        if not attachment:
            raise UserError(_("Attach the document (PDF or picture) to read first."))
        values = self.env['local.ai.document']._read_invoice(attachment, self.company_id)
        values['partner'] = self._local_ai_find_partner(values)
        filled, kept, warnings = self._local_ai_apply(values)
        self._local_ai_post_note(attachment, values, filled, kept, warnings)
        return values

    def action_local_ai_read_document(self):
        self.ensure_one()
        self.check_access('write')
        self._local_ai_read()
        self.sudo().write({'ai_state': 'done', 'ai_error': False, 'ai_date': fields.Datetime.now()})
        return True

    def _local_ai_process(self):
        record = self.with_company(self.company_id)
        if record._local_ai_can_read():
            record._local_ai_read()

    def _local_ai_post_note(self, attachment, values, filled, kept, warnings):
        currency = values['currency'] or self.currency_id

        def amount(value):
            return formatLang(self.env, value, currency_obj=currency) if value is not None else None

        partner_name = values['partner_name'] or ''
        if values['partner']:
            partner_text = _("%(name)s (contact: %(contact)s)", name=partner_name or values['partner'].display_name,
                             contact=values['partner'].display_name)
        elif partner_name or values['vat']:
            partner_text = _("%s (no matching contact)", ' '.join(filter(None, [partner_name, values['vat']])))
        else:
            partner_text = None
        rows = [
            (_("Vendor"), partner_text),
            (_("Number"), values['reference']),
            (_("Date"), values['date'] and format_date(self.env, values['date'])),
            (_("Due date"), values['date_due'] and format_date(self.env, values['date_due'])),
            (_("Currency"), values['currency_code']),
            (_("Untaxed amount"), amount(values['untaxed'])),
            (_("Taxes"), amount(values['tax'])),
            (_("Total"), amount(values['total'])),
            (_("Description"), values['description']),
        ]
        source = _("text") if values.get('source') == 'text' else _("picture")
        body = Markup('<p><b>%s</b></p>') % _(
            "Document %(name)s read by the AI (%(source)s): check the values before validating.",
            name=attachment.name, source=source)
        items = [Markup('<li>%s : %s</li>') % (label, value) for label, value in rows if value]
        body += Markup('<ul>%s</ul>') % Markup('').join(items) if items else Markup('<p>%s</p>') % _(
            "Nothing could be read on the document.")
        if filled:
            body += Markup('<p>%s</p>') % _("Filled: %s.", ', '.join(filled))
        if kept:
            body += Markup('<p>%s</p>') % _("Left as they were (already entered): %s.", ', '.join(kept))
        for warning in warnings:
            body += Markup('<p>⚠ %s</p>') % warning
        self.message_post(body=body, message_type='comment', subtype_xmlid='mail.mt_note')
