# -*- coding: utf-8 -*-
"""Official French public holidays, imported from the government's API
"Jours fériés" (https://calendrier.api.gouv.fr, listed on api.gouv.fr) into
the public holidays of Odoo (global time off, resource.calendar.leaves)."""
import json
import logging
import time as time_module
from datetime import date, datetime, time, timedelta

import pytz
import requests

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError

from odoo.addons.hr_timesheet_consistency.models.timesheet_day_rules import easter_date

_logger = logging.getLogger(__name__)

API_URL = 'https://calendrier.api.gouv.fr/jours-feries/%s.json'
API_SOURCE = 'calendrier.api.gouv.fr'
API_TIMEOUT = 20  # seconds, for the connection and for each read
API_MAX_SECONDS = 60  # for the whole answer
API_MAX_BYTES = 1000000  # the answers weigh about 10 kB
# Plausible number of public holidays in a year (10 to 13 depending on the zone and the year):
# an answer outside these bounds is rejected, so that an incomplete or abnormal answer never
# removes or floods the public holidays.
MIN_YEAR_HOLIDAYS = 8
MAX_YEAR_HOLIDAYS = 20
DEFAULT_TZ = 'Europe/Paris'
CRON_XMLID = 'hr_holidays_public_fr.ir_cron_import_public_holidays'
ADMIN_GROUPS = ('hr_holidays.group_hr_holidays_manager', 'base.group_system')
# Context key holding a UTC datetime: the public holidays ending before it get
# no generated timesheets (see resource.calendar.leaves._generate_timesheeets).
TIMESHEETS_FROM_KEY = 'hr_holidays_public_fr_timesheets_from'

# Zones of the API: https://calendrier.api.gouv.fr/jours-feries/<zone>.json
ZONES = [
    ('metropole', 'Metropolitan France'),
    ('alsace-moselle', 'Alsace-Moselle'),
    ('guadeloupe', 'Guadeloupe'),
    ('guyane', 'French Guiana'),
    ('la-reunion', 'Réunion'),
    ('martinique', 'Martinique'),
    ('mayotte', 'Mayotte'),
    ('nouvelle-caledonie', 'New Caledonia'),
    ('polynesie-francaise', 'French Polynesia'),
    ('saint-barthelemy', 'Saint Barthélemy'),
    ('saint-martin', 'Saint Martin'),
    ('saint-pierre-et-miquelon', 'Saint Pierre and Miquelon'),
    ('wallis-et-futuna', 'Wallis and Futuna'),
]
# Default zone of a company, from the country of its address
COUNTRY_ZONES = {
    'FR': 'metropole', 'GP': 'guadeloupe', 'GF': 'guyane', 'RE': 'la-reunion', 'MQ': 'martinique',
    'YT': 'mayotte', 'NC': 'nouvelle-caledonie', 'PF': 'polynesie-francaise', 'BL': 'saint-barthelemy',
    'MF': 'saint-martin', 'PM': 'saint-pierre-et-miquelon', 'WF': 'wallis-et-futuna',
}


def whit_monday(year):
    """Whit Monday (Lundi de Pentecôte) of ``year``."""
    return easter_date(year) + timedelta(days=50)


class HrPublicHolidayFr(models.Model):
    """One official public holiday of a company, and what the import did with
    it. The record remembers a public holiday deleted in Odoo, so that the
    next imports do not create it again."""
    _name = 'hr.public.holiday.fr'
    _description = 'Official French public holiday'
    _order = 'date desc, company_id'

    company_id = fields.Many2one(
        'res.company', string='Company', required=True, readonly=True, index=True, ondelete='cascade')
    date = fields.Date(required=True, readonly=True)
    name = fields.Char(string='Public Holiday', required=True, readonly=True)
    zone = fields.Selection(ZONES, required=True, readonly=True)
    state = fields.Selection([
        ('imported', 'Imported'),
        ('existing', 'Already recorded'),
        ('worked', 'Worked day'),
        ('deleted', 'Deleted in Odoo'),
        ('withdrawn', 'No longer official'),
    ], string='Status', required=True, readonly=True,
        help="Imported: recorded in the public holidays of Odoo by the import.\n"
             "Already recorded: a public holiday of Odoo already overlapped the day; it is left as it is.\n"
             "Worked day: Whit Monday, left out as a worked day (journée de solidarité).\n"
             "Deleted in Odoo: the imported public holiday was deleted; it is not imported again.\n"
             "No longer official: the government no longer publishes it.")
    leave_id = fields.Many2one(
        'resource.calendar.leaves', string='Odoo Public Holiday', readonly=True,
        index='btree_not_null', ondelete='set null')

    _company_date_uniq = models.Constraint(
        'UNIQUE(company_id, date)',
        'An official public holiday is recorded once per company and date.',
    )

    # ------------------------------------------------------------------
    # Used by the timesheet rules
    # ------------------------------------------------------------------
    @api.model
    def _is_year_imported(self, year, companies):
        """Whether the official public holidays of ``year`` have been imported
        for each of ``companies``: the public holidays of Odoo are then the
        reference, instead of the computed French public holidays."""
        if not companies:
            return False
        groups = self.sudo()._read_group([
            ('company_id', 'in', companies.ids),
            ('date', '>=', date(year, 1, 1)),
            ('date', '<=', date(year, 12, 31)),
        ], ['company_id'])
        return len(groups) == len(companies)

    # ------------------------------------------------------------------
    # Government API
    # ------------------------------------------------------------------
    @api.model
    def _fetch_official_holidays(self, zone):
        """Public holidays of ``zone`` published by the government, as
        ``{date: label}``: about twenty years back and five years ahead.

        :raise UserError: when the API cannot be reached or does not answer
            with a list of public holidays
        """
        if zone not in dict(ZONES):
            raise UserError(_("Unknown zone of public holidays: %s", zone))
        url = API_URL % zone
        try:
            deadline = time_module.monotonic() + API_MAX_SECONDS
            body = b''
            with requests.get(url, timeout=API_TIMEOUT, headers={'Accept': 'application/json'}, stream=True) as response:
                response.raise_for_status()
                for chunk in response.iter_content(chunk_size=65536):
                    body += chunk
                    if len(body) > API_MAX_BYTES:
                        raise ValueError("answer larger than %s bytes" % API_MAX_BYTES)
                    if time_module.monotonic() > deadline:
                        raise ValueError("no complete answer after %s seconds" % API_MAX_SECONDS)
            payload = json.loads(body.decode('utf-8'))
        except (requests.RequestException, ValueError) as error:
            raise UserError(_(
                "The public holidays could not be downloaded from %(url)s: %(error)s",
                url=url, error=error)) from error
        return self._parse_official_holidays(payload, url)

    @api.model
    def _parse_official_holidays(self, payload, url):
        """``{date: label}`` from the answer of the API, ``{"YYYY-MM-DD":
        label}``. The whole answer is rejected when one entry is not valid."""
        if not isinstance(payload, dict) or not payload:
            raise UserError(_("Unexpected answer from %s: no public holiday.", url))
        holidays = {}
        for key, label in payload.items():
            try:
                day = date.fromisoformat(key)
            except (TypeError, ValueError):
                day = None
            if not day or not isinstance(label, str) or not label.strip():
                raise UserError(_(
                    "Unexpected answer from %(url)s: %(entry)s is not a public holiday.",
                    url=url, entry=repr((key, label))[:100]))
            holidays[day] = ' '.join(label.split())[:100]
        return holidays

    # ------------------------------------------------------------------
    # Import
    # ------------------------------------------------------------------
    @api.model
    def action_import(self):
        """Button of the lists of public holidays."""
        return self._action_import(self.env.companies)

    @api.model
    def _action_import(self, companies):
        """Import now for ``companies`` and notify the result."""
        if not any(self.env.user.has_group(group) for group in ADMIN_GROUPS):
            raise AccessError(_("Only time off administrators can import the public holidays."))
        companies = companies.filtered('fr_public_holidays_zone')
        if not companies:
            raise UserError(_(
                "Choose the zone of the official public holidays first: Settings, Employees, "
                "French Public Holidays."))
        results = self.sudo()._import_public_holidays(companies, raise_errors=True)
        created = sum(result['created'] for result in results.values())
        removed = sum(result['removed'] for result in results.values())
        if created or removed:
            message = _(
                "%(created)s public holiday(s) imported and %(removed)s removed, from %(source)s.",
                created=created, removed=removed, source=API_SOURCE)
        else:
            message = _("The public holidays are up to date with %s.", API_SOURCE)
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'type': 'success',
                'title': _("Official public holidays"),
                'message': message,
                'next': {'type': 'ir.actions.client', 'tag': 'soft_reload'},
            },
        }

    @api.model
    def _cron_import(self):
        """Scheduled action. Errors are logged and shown in the settings
        instead of failing the scheduled action, which Odoo would deactivate
        after a few failures (the API may be unreachable for some days)."""
        self._import_public_holidays(raise_errors=False)

    @api.model
    def _import_public_holidays(self, companies=None, raise_errors=False, today=None):
        """Import the official public holidays of the current and the next
        year into the public holidays of ``companies`` (default: every
        company), for the companies having a zone.

        :param raise_errors: raise the errors instead of logging them and
            keeping them on the company
        :param today: day of the import (tests)
        :return: ``{company: {'created': int, 'removed': int}}``
        """
        if companies is None:
            companies = self.env['res.company'].sudo().search([])
        results = {}
        official_by_zone = {}
        for company in companies.sudo().filtered('fr_public_holidays_zone'):
            zone = company.fr_public_holidays_zone
            try:
                if zone not in official_by_zone:
                    try:
                        official_by_zone[zone] = self._fetch_official_holidays(zone)
                    except UserError as error:
                        official_by_zone[zone] = error
                if isinstance(official_by_zone[zone], UserError):
                    raise official_by_zone[zone]
                with self.env.cr.savepoint():
                    results[company] = self._import_company_holidays(company, official_by_zone[zone], today=today)
            except (UserError, ValidationError) as error:
                if raise_errors:
                    raise
                message = str(error.args[0] if error.args else error)
                _logger.warning("Official public holidays not imported for company %s: %s", company.id, message)
                company.fr_public_holidays_sync_error = message[:1000]
                continue
            company.write({
                'fr_public_holidays_sync_date': fields.Datetime.now(),
                'fr_public_holidays_sync_error': False,
            })
        return results

    @api.model
    def _import_company_holidays(self, company, official, today=None):
        """Bring the public holidays of ``company`` in line with ``official``
        (``{date: label}``) for the current and the next year.

        * An official public holiday is created in Odoo, unless a public
          holiday of the company already overlaps the day, it is Whit Monday
          while Whit Monday is worked, or it was deleted in Odoo after a
          previous import.
        * An imported public holiday still to come is removed when the
          government no longer publishes it, or when it is Whit Monday and
          Whit Monday becomes a worked day.
        * The past is never rewritten: a past public holiday is never
          removed, a past Whit Monday left out as a worked day stays a worked
          day, and no timesheet is generated for the days already past.
        * A public holiday recorded by hand is never changed nor removed.
        """
        self = self.sudo()
        zone = company.fr_public_holidays_zone
        tz = self._get_company_tz(company)
        today = today or datetime.now(tz).date()
        years = (today.year, today.year + 1)
        official_by_year = {
            year: {day: label for day, label in official.items() if day.year == year} for year in years}
        for year, year_official in official_by_year.items():
            if not MIN_YEAR_HOLIDAYS <= len(year_official) <= MAX_YEAR_HOLIDAYS:
                raise UserError(_(
                    "Unexpected answer from %(source)s: %(count)s public holidays for %(year)s in zone %(zone)s. "
                    "Nothing was changed.",
                    source=API_SOURCE, count=len(year_official), year=year, zone=zone))
        # One import at a time per company: a concurrent import waits here, then fails with a
        # serialization error (the first one updates the company) and is run again with fresh data.
        self.env.cr.execute('SELECT id FROM res_company WHERE id = %s FOR UPDATE', (company.id,))
        whit_monday_worked = self.env['hr.timesheet.day.rules']._whit_monday_worked()
        # only the employees of the company get the generated timesheets
        Leave = self.env['resource.calendar.leaves'].with_context(**{
            'allowed_company_ids': company.ids,
            TIMESHEETS_FROM_KEY: fields.Datetime.to_string(self._day_bounds(today, tz)[0]),
        })
        counts = {'created': 0, 'removed': 0}
        for year in years:
            year_official = official_by_year[year]
            worked_day = whit_monday(year) if whit_monday_worked else None
            rows = self.search([
                ('company_id', '=', company.id),
                ('date', '>=', date(year, 1, 1)),
                ('date', '<=', date(year, 12, 31)),
            ])
            rows_by_date = {row.date: row for row in rows}

            # 1. The imported public holidays that must go: only those still to come.
            for row in rows:
                if row.state == 'imported' and not row.leave_id:
                    row.state = 'deleted'  # deleted without the ORM
                official_day = row.date in year_official
                if official_day and not (row.date == worked_day and row.state == 'imported'):
                    continue
                if row.state == 'imported' and row.date >= today:
                    row.leave_id.unlink()
                    counts['removed'] += 1
                    row.state = 'worked' if official_day else 'withdrawn'
                elif not official_day and row.state not in ('deleted', 'withdrawn'):
                    # A past imported public holiday is kept, with its link. A public holiday
                    # recorded by hand is not the import's: its link is forgotten.
                    row.write({
                        'state': 'withdrawn',
                        'leave_id': row.leave_id.id if row.state == 'imported' else False,
                    })

            # 2. The official public holidays to record.
            start, end = self._day_bounds(date(year, 1, 1), tz)[0], self._day_bounds(date(year, 12, 31), tz)[1]
            company_leaves = Leave.search([
                ('resource_id', '=', False),
                ('company_id', '=', company.id),
                ('date_from', '<=', end),
                ('date_to', '>=', start),
            ])
            to_import = []
            for day, label in sorted(year_official.items()):
                row = rows_by_date.get(day)
                if row:
                    if row.name != label:
                        if row.state == 'imported' and row.leave_id.name == row.name:
                            row.leave_id.name = label
                        row.name = label
                    if row.zone != zone:
                        row.zone = zone
                    if row.state in ('imported', 'deleted'):
                        continue
                    if row.state == 'worked' and (day == worked_day or day < today):
                        continue  # still a worked day, or past: a past day keeps what it was
                day_start, day_end = self._day_bounds(day, tz)
                # same overlap rule as the constraint of hr_holidays on public holidays
                covering = company_leaves.filtered(
                    lambda leave: leave.date_from <= day_end and leave.date_to >= day_start)
                if row and row.state == 'withdrawn' and row.leave_id and row.leave_id in covering:
                    # official again, and the public holiday imported before is still there
                    values = {'state': 'imported'}
                elif covering:
                    values = {'state': 'existing', 'leave_id': covering[0].id}
                elif day == worked_day:
                    values = {'state': 'worked', 'leave_id': False}
                else:
                    to_import.append((day, label, row))
                    continue
                if row:
                    row.write(values)
                else:
                    self.create(dict(values, company_id=company.id, date=day, name=label, zone=zone))

            if to_import:
                leaves = Leave.create([{
                    'name': label,
                    'company_id': company.id,
                    'calendar_id': False,
                    'date_from': self._day_bounds(day, tz)[0],
                    'date_to': self._day_bounds(day, tz)[1],
                    'time_type': 'leave',
                } for day, label, _row in to_import])
                for (day, label, row), leave in zip(to_import, leaves):
                    values = {'state': 'imported', 'leave_id': leave.id}
                    if row:
                        row.write(values)
                    else:
                        self.create(dict(values, company_id=company.id, date=day, name=label, zone=zone))
                counts['created'] += len(leaves)
        if counts['created'] or counts['removed']:
            _logger.info("Official public holidays of company %s (%s): %s created, %s removed.",
                         company.id, zone, counts['created'], counts['removed'])
        return counts

    @api.model
    def _get_company_tz(self, company):
        """Time zone of the public holidays of ``company``: the one of its
        working schedule."""
        for name in (company.resource_calendar_id.tz, company.partner_id.tz):
            if name:
                try:
                    return pytz.timezone(name)
                except pytz.UnknownTimeZoneError:
                    continue
        return pytz.timezone(DEFAULT_TZ)

    @api.model
    def _day_bounds(self, day, tz):
        """First and last second of ``day`` in ``tz``, as naive UTC datetimes
        (how Odoo stores a public holiday entered for a whole day)."""
        start = tz.localize(datetime.combine(day, time.min)).astimezone(pytz.utc).replace(tzinfo=None)
        end = tz.localize(datetime.combine(day, time(23, 59, 59))).astimezone(pytz.utc).replace(tzinfo=None)
        return start, end
