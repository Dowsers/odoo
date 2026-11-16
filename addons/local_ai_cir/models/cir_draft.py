# -*- coding: utf-8 -*-
import re
from collections import defaultdict
from datetime import date

from markupsafe import Markup

from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools import format_date, formatLang, html2plaintext

from .prompts import CIR_CONTEXT, CIR_SECTIONS, CIR_SUMMARY, CIR_SYSTEM, CIR_TO_COMPLETE, CIR_TOO_THIN

ADMIN_GROUP = 'hr_timesheet.group_timesheet_manager'
CHUNK_CHARS = 2000      # timesheet descriptions summarized per request
SECTION_TITLE = re.compile(r"Rédige la section « ([^»]+) »")
PREAMBLE = re.compile(r"^(voici|ci-dessous|bien sûr|d'accord)\b.*:\s*$", re.IGNORECASE)
MIN_ENTRIES = 5         # under this number of described timesheets...
MIN_DESCRIPTION = 150   # ...and this length of task description, the AI is not asked (it would invent)
SUMMARY_CHARS = 3000    # summaries given to each section request
SECTION_TOKENS = 450


class LocalAICirDraft(models.Model):
    _name = 'local.ai.cir.draft'
    _inherit = ['local.ai.queue.mixin']
    _description = 'CIR Dossier Draft'
    _order = 'year desc, total_days desc, id'

    name = fields.Char(compute='_compute_name', store=True)
    year = fields.Integer(required=True, default=lambda self: fields.Date.context_today(self).year)
    task_id = fields.Many2one('project.task', string='R&D Task', required=True, ondelete='cascade', index=True)
    project_id = fields.Many2one(related='task_id.project_id', store=True)
    company_id = fields.Many2one(related='task_id.company_id', store=True)
    total_days = fields.Float(string='Days', readonly=True, digits=(16, 2))
    employee_count = fields.Integer(string='People', readonly=True)
    line_count = fields.Integer(string='Timesheets', readonly=True)
    described_count = fields.Integer(string='Described Timesheets', readonly=True)
    facts = fields.Html(string='Facts', readonly=True,
                        help="Computed by Odoo from the timesheets, not by the AI.")
    objectives = fields.Html(string='Objectives')
    obstacles = fields.Html(string='Scientific and Technical Obstacles')
    work = fields.Html(string='Work Carried Out')
    results = fields.Html(string='Results and Progress')
    model_used = fields.Char(string='AI Model', readonly=True)

    _year_task_uniq = models.Constraint('UNIQUE(year, task_id)', 'There is already a draft for this task and year.')

    @api.depends('year', 'task_id.name', 'project_id.name')
    def _compute_name(self):
        for draft in self:
            draft.name = _("CIR %(year)s - %(task)s", year=draft.year, task=draft.task_id.display_name or '')

    def action_generate(self):
        if not self.env.user.has_group(ADMIN_GROUP):
            raise UserError(_("Only timesheet administrators can prepare the CIR dossier."))
        self._local_ai_enqueue()
        return True

    # ------------------------------------------------------------------
    # Facts computed by Odoo
    # ------------------------------------------------------------------
    def _collect(self):
        """Timesheets of the task in the year: facts and dated descriptions."""
        self.ensure_one()
        lines = self.env['account.analytic.line'].sudo().search([
            ('task_id', '=', self.task_id.id),
            ('project_id', '!=', False),
            ('date', '>=', date(self.year, 1, 1)),
            ('date', '<=', date(self.year, 12, 31)),
        ], order='date, id')
        rules = self.env['hr.timesheet.day.rules']
        days_per_employee = defaultdict(float)
        hours_per_day = {}
        entries, seen = [], set()
        for line in lines:
            employee = line.employee_id
            if employee not in hours_per_day:
                hours_per_day[employee] = rules._get_hours_per_day(employee) if employee else 8.0
            days_per_employee[employee] += max(line.unit_amount, 0.0) / (hours_per_day[employee] or 8.0)
            text = ' '.join((line.name or '').split())
            if line.cir_description_quality in ('ok', 'short') and text.lower() not in seen:
                seen.add(text.lower())
                entries.append(f"{line.date.strftime('%m/%Y')} : {text}")
        return {
            'lines': lines,
            'days_per_employee': {employee: round(days, 2) for employee, days in days_per_employee.items() if days},
            'entries': entries,
            'first': lines[:1].date,
            'last': lines[-1:].date,
        }

    def _facts_html(self, data):
        people = sorted(data['days_per_employee'].items(), key=lambda item: -item[1])
        period = _("from %(first)s to %(last)s", first=format_date(self.env, data['first']),
                   last=format_date(self.env, data['last'])) if data['first'] else _("no timesheet")
        rows = [
            (_("Period"), period),
            (_("Time spent"), _("%s days", formatLang(self.env, sum(data['days_per_employee'].values()), digits=2))),
            (_("Timesheets"), _("%(count)s, of which %(described)s with a description",
                                count=len(data['lines']), described=len(data['entries']))),
            (_("People"), ', '.join(f"{employee.name or _('Unknown')} ({formatLang(self.env, days, digits=2)} j)"
                                    for employee, days in people) or '-'),
        ]
        body = Markup('').join(Markup('<tr><th class="pe-3">%s</th><td>%s</td></tr>') % row for row in rows)
        return Markup('<table class="table table-sm o_local_ai_cir_facts">%s</table>') % body

    # ------------------------------------------------------------------
    # Drafting (local_ai queue)
    # ------------------------------------------------------------------
    @api.model
    def _clean_section(self, answer, instruction):
        """Answer without the introduction ("Voici la section...:") nor the
        title of the section that the model sometimes adds."""
        match = SECTION_TITLE.search(instruction)
        title = match.group(1).strip().lower() if match else None
        lines = (answer or '').strip().splitlines()
        while lines:
            first = re.sub(r'^[#*\s]+|[*\s]+$', '', lines[0]).strip()
            if not first or PREAMBLE.match(first):
                lines.pop(0)
                continue
            if title and first.lower().strip('«» ').startswith(title):
                rest = first[len(title):].lstrip('«» ').lstrip(':').strip() if first.lower().startswith(title) else ''
                if rest:
                    lines[0] = rest
                    break
                lines.pop(0)
                continue
            break
        return '\n'.join(lines).strip()

    def _local_ai_process(self):
        LocalAI = self.env['local.ai']
        data = self._collect()
        values = {
            'facts': self._facts_html(data),
            'total_days': sum(data['days_per_employee'].values()),
            'employee_count': len(data['days_per_employee']),
            'line_count': len(data['lines']),
            'described_count': len(data['entries']),
        }
        description = ' '.join(html2plaintext(self.task_id.description or '').split())[:800]
        if len(data['entries']) < MIN_ENTRIES and len(description) < MIN_DESCRIPTION:
            # too little to write from: never let the model invent the dossier
            values.update({section: LocalAI._text_to_html(text) for section, text in CIR_TO_COMPLETE.items()})
            if data['entries']:
                values['work'] = LocalAI._text_to_html('\n'.join(
                    [CIR_TOO_THIN.format(described=len(data['entries']), lines=len(data['lines'])), '']
                    + [f"- {entry}" for entry in data['entries']]))
            values['model_used'] = False
            self.write(values)
            return

        summaries = []
        chunk, size = [], 0
        for entry in data['entries'] + [None]:
            if entry is None or (chunk and size + len(entry) > CHUNK_CHARS):
                if chunk:
                    summaries.append(LocalAI._chat(
                        [{'role': 'user', 'content': CIR_SUMMARY.format(
                            task=self.task_id.name, project=self.project_id.name, entries='\n'.join(chunk))}],
                        system=CIR_SYSTEM, temperature=0.1, max_tokens=350))
                chunk, size = [], 0
            if entry is not None:
                chunk.append(entry)
                size += len(entry) + 1
        work = '\n'.join(summaries)[:SUMMARY_CHARS] or "aucune description exploitable"
        context = CIR_CONTEXT.format(
            task=self.task_id.name,
            project=self.project_id.name,
            description=description or 'aucune',
            period=(f"du {data['first'].strftime('%d/%m/%Y')} au {data['last'].strftime('%d/%m/%Y')}"
                    if data['first'] else 'aucune saisie'),
            days=formatLang(self.env, values['total_days'], digits=2),
            people=values['employee_count'],
            work=work,
        )
        for section, instruction in CIR_SECTIONS.items():
            answer = LocalAI._chat([{'role': 'user', 'content': f"{context}\n\n{instruction}"}],
                                   system=CIR_SYSTEM, temperature=0.2, max_tokens=SECTION_TOKENS)
            answer = self._clean_section(answer, instruction)
            values[section] = LocalAI._text_to_html(answer) or LocalAI._text_to_html(CIR_TO_COMPLETE[section])
        values['model_used'] = LocalAI._get_config()['model']
        self.write(values)
