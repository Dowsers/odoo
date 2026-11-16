# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools import html2plaintext

from .prompts import SUGGEST_SYSTEM

MAX_LINES_PER_REQUEST = 300
EMPTY_DESCRIPTIONS = {'', '/', '-', '.', '?'}


class AccountAnalyticLine(models.Model):
    _name = 'account.analytic.line'
    _inherit = ['account.analytic.line', 'local.ai.queue.mixin']

    cir_description_quality = fields.Selection([
        ('missing', 'Missing'),
        ('short', 'Too Short'),
        ('ok', 'Described'),
    ], string='CIR Description', compute='_compute_cir_description_quality', store=True, index='btree_not_null',
        help="How well the description justifies an activity for the CIR: missing (\"/\"), too short "
             "(less than 3 words or 15 characters), or described. Empty for absences and analytic lines.")
    ai_suggestion = fields.Char(string='AI Suggestion', copy=False,
                                help="Description suggested by the local AI, to apply or edit.")

    @api.depends('name', 'project_id', 'task_id', 'task_id.timesheet_absence')
    def _compute_cir_description_quality(self):
        absence_ids = set(self.env['hr.timesheet.day.rules']._get_absence_tasks().ids)
        for line in self:
            if not line.project_id or line.task_id.id in absence_ids:
                line.cir_description_quality = False
                continue
            text = ' '.join((line.name or '').split())
            if text in EMPTY_DESCRIPTIONS:
                line.cir_description_quality = 'missing'
            elif len(text) < 15 or len(text.split()) < 3:
                line.cir_description_quality = 'short'
            else:
                line.cir_description_quality = 'ok'

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------
    def action_local_ai_suggest(self):
        lines = self.filtered(lambda line: line.cir_description_quality in ('missing', 'short'))
        if not lines:
            raise UserError(_("Select timesheets whose description is missing or too short."))
        if len(lines) > MAX_LINES_PER_REQUEST:
            raise UserError(_("Select at most %s timesheets at a time.", MAX_LINES_PER_REQUEST))
        # only the timesheets the user may modify
        lines.check_access('write')
        lines._check_can_write({'name': True})
        lines._local_ai_enqueue()
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'type': 'info',
                'title': _("Local AI"),
                'message': _("%s description(s) requested. Reload the list in a moment to see the suggestions.",
                             len(lines)),
                'next': {'type': 'ir.actions.client', 'tag': 'soft_reload'},
            },
        }

    def action_local_ai_apply(self):
        for line in self.filtered('ai_suggestion'):
            line.write({'name': line.ai_suggestion, 'ai_suggestion': False, 'ai_state': False, 'ai_error': False})
        return True

    def action_local_ai_dismiss(self):
        self.filtered(lambda line: line.ai_suggestion or line.ai_state).write(
            {'ai_suggestion': False, 'ai_state': False, 'ai_error': False})
        return True

    # ------------------------------------------------------------------
    # Processing (local_ai queue)
    # ------------------------------------------------------------------
    def _local_ai_suggestion_prompt(self):
        self.ensure_one()
        Line = self.env['account.analytic.line'].sudo()
        scope = [('task_id', '=', self.task_id.id)] if self.task_id else [('project_id', '=', self.project_id.id),
                                                                          ('task_id', '=', False)]
        described = Line.search(scope + [('cir_description_quality', '=', 'ok'), ('id', '!=', self.id)],
                                order='date desc, id desc', limit=200)

        def closest(lines, limit):
            texts = []
            for line in sorted(lines, key=lambda line: abs((line.date - self.date).days)):
                text = ' '.join(line.name.split())
                if text.lower() not in (known.lower() for known in texts):
                    texts.append(text)
                if len(texts) == limit:
                    break
            return '\n'.join('- ' + text for text in texts) or 'aucune'

        own = closest(described.filtered(lambda line: line.employee_id == self.employee_id), 8)
        team = closest(described.filtered(lambda line: line.employee_id != self.employee_id), 5)
        description = ' '.join(html2plaintext(self.task_id.description or '').split())[:600] or 'aucune'
        return (
            f"Projet : {self.project_id.name}\n"
            f"Tâche : {self.task_id.name or 'aucune'}\n"
            f"Description de la tâche : {description}\n"
            f"Date de la saisie : {self.date.strftime('%d/%m/%Y')}\n"
            f"Description actuelle : {self.name or '/'}\n\n"
            f"Descriptions déjà saisies par la même personne sur cette tâche :\n{own}\n\n"
            f"Descriptions saisies par l'équipe sur cette tâche :\n{team}\n\n"
            f"Propose la description de la saisie de temps du {self.date.strftime('%d/%m/%Y')}."
        )

    def _local_ai_process(self):
        LocalAI = self.env['local.ai']
        answer = LocalAI._chat([{'role': 'user', 'content': self._local_ai_suggestion_prompt()}],
                               system=SUGGEST_SYSTEM, temperature=0.2, max_tokens=80)
        suggestion = LocalAI._first_line(answer)
        if not suggestion:
            raise UserError(_("The local AI did not suggest a description."))
        self.write({'ai_suggestion': suggestion})
