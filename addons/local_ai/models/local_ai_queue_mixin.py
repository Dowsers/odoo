# -*- coding: utf-8 -*-
import logging

from odoo import _, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)
CRON_XMLID = 'local_ai.ir_cron_local_ai_queue'


class LocalAIQueueMixin(models.AbstractModel):
    """Records processed by the local AI in the background: _local_ai_enqueue()
    puts them in the queue, the scheduled action calls _local_ai_process() on
    each of them."""
    _name = 'local.ai.queue.mixin'
    _description = 'Local AI processing queue'

    ai_state = fields.Selection([
        ('queued', 'Queued'),
        ('done', 'Done'),
        ('error', 'Error'),
    ], string='AI Status', copy=False, readonly=True, index='btree_not_null')
    ai_error = fields.Char(string='AI Error', copy=False, readonly=True)
    ai_date = fields.Datetime(string='AI Date', copy=False, readonly=True,
                              help="When the record was queued, then processed.")

    def _local_ai_enqueue(self):
        if not self:
            return
        self.env['local.ai']._get_config()  # fails early on a broken configuration
        self.sudo().write({'ai_state': 'queued', 'ai_error': False, 'ai_date': fields.Datetime.now()})
        cron = self.env.ref(CRON_XMLID, raise_if_not_found=False)
        if cron:
            cron.sudo()._trigger()

    def _local_ai_process(self):
        """Process one record (called with sudo by the scheduled action)."""
        raise NotImplementedError()

    def _local_ai_run(self):
        self.ensure_one()
        try:
            with self.env.cr.savepoint():
                self._local_ai_process()
        except UserError as error:
            self.write({'ai_state': 'error', 'ai_error': str(error.args[0] if error.args else error)[:500],
                        'ai_date': fields.Datetime.now()})
        except Exception as error:  # noqa: BLE001 - a broken record must not block the queue
            _logger.exception("Local AI: processing of %s failed", self)
            self.write({'ai_state': 'error', 'ai_error': _("Unexpected error: %s", error)[:500],
                        'ai_date': fields.Datetime.now()})
        else:
            self.write({'ai_state': 'done', 'ai_error': False, 'ai_date': fields.Datetime.now()})
