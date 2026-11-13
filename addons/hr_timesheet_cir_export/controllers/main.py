# -*- coding: utf-8 -*-
from werkzeug.exceptions import BadRequest, Forbidden

from odoo import http
from odoo.http import content_disposition, request

from ..models.timesheet_cir_export import ADMIN_GROUP


class TimesheetCirExportController(http.Controller):

    @http.route('/hr_timesheet_cir_export/download', type='http', auth='user', methods=['POST'], csrf=True)
    def download(self, year=None, month=None, **kwargs):
        """Download the ZIP of the CIR timesheets.

        Without parameters: current year, stopped at the previous complete
        month. ``year`` / ``month`` (1-12) may be given to export another
        period (the whole year up to ``month``).
        """
        if not request.env.user.has_group(ADMIN_GROUP):
            raise Forbidden()
        exporter = request.env['hr.timesheet.cir.export']
        default_year, default_month = exporter._default_period()
        try:
            year = int(year) if year else default_year
            month = int(month) if month else default_month
        except ValueError:
            raise BadRequest('Invalid year or month')
        if not (1 <= month <= 12 and 2000 <= year <= 2100):
            raise BadRequest('Invalid year or month')

        content, filename = exporter._generate_zip(year, month)
        return request.make_response(content, headers=[
            ('Content-Type', 'application/zip'),
            ('Content-Disposition', content_disposition(filename)),
            ('Content-Length', str(len(content))),
        ])
