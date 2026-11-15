# -*- coding: utf-8 -*-
from odoo import models


class PublisherWarrantyContract(models.AbstractModel):
    _inherit = 'publisher_warranty.contract'

    def update_notification(self, cron_mode=True):
        """Local instance: nothing is sent to Odoo's publisher warranty
        service (database identifier, number of users, installed modules).
        The scheduled action is deactivated as well (data/data.xml)."""
        return True
