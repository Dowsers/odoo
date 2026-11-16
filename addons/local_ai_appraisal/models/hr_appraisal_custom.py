# -*- coding: utf-8 -*-
from odoo import _, fields, models
from odoo.exceptions import UserError

SUMMARY_SYSTEM = (
    "Tu aides un service RH à synthétiser un entretien d'évaluation annuel. Tu écris en français, de façon "
    "factuelle, bienveillante et neutre. Tu n'utilises QUE les informations fournies : tu n'inventes ni "
    "appréciation, ni note, ni objectif. Tu ne mentionnes pas le nom des personnes."
)
SUMMARY_REQUEST = (
    "Voici le contenu de l'entretien d'évaluation.\n\n{content}\n\n"
    "Rédige la synthèse avec exactement ces quatre parties, chacune précédée de son titre sur une ligne :\n"
    "Synthèse : 3 à 5 phrases.\n"
    "Points forts : 2 à 5 puces commençant par « - ».\n"
    "Axes de progrès : 2 à 5 puces commençant par « - ».\n"
    "Objectifs à suivre : puces commençant par « - ».\n"
    "Si une partie n'est pas renseignée dans l'entretien, écris « Non renseigné » pour cette partie."
)
MAX_CONTENT = 9000


class HrAppraisalCustom(models.Model):
    _inherit = 'hr.appraisal.custom'

    ai_summary = fields.Html(string='AI Summary', copy=False,
                             help="Written by the local AI from the appraisal, to check and edit.")
    ai_summary_date = fields.Datetime(string='AI Summary Date', copy=False, readonly=True)

    def _local_ai_summary_content(self):
        """Text of the appraisal given to the AI (no names, no remuneration)."""
        self.ensure_one()
        parts = []

        def add(title, text):
            text = (text or '').strip()
            if text:
                parts.append(f"{title} : {text}")

        add("Poste", self.job_id.name)
        add("Année", self.appraisal_year)
        add("Performance globale", self._label_of(self, 'global_performance'))
        add("Commentaire sur la performance globale", self.global_performance_comment)
        add("Note globale", self._label_of(self, 'overall_rating'))
        add("Auto-évaluation", self.self_assessment)
        add("Évaluation du manager", self.manager_assessment)
        add("Retour du collaborateur", self.employee_feedback)
        add("Retour du manager", self.manager_feedback)
        add("Points forts notés", self.strengths)
        add("Axes d'amélioration notés", self.areas_improvement)
        add("Charge de travail", ' '.join(filter(None, [self._label_of(self, 'workload_remarks'),
                                                        self.workload_notes or ''])))
        add("Notes de l'entretien", self.interview_notes)
        criteria = []
        for line in self.criteria_ids:
            details = [f"auto-évaluation : {self._label_of(line, 'self_rating')}" if line.self_rating else '',
                       f"manager : {self._label_of(line, 'manager_rating')}" if line.manager_rating else '',
                       f"commentaire : {line.self_comment}" if line.self_comment else '',
                       f"commentaire du manager : {line.manager_comment}" if line.manager_comment else '']
            criteria.append(f"- {line.name}" + (f" ({line.category})" if line.category else '')
                            + (" : " + ' ; '.join(filter(None, details)) if any(details) else ''))
        add("Critères", '\n' + '\n'.join(criteria) if criteria else '')
        objectives = []
        for objective in self.objective_past_ids | self.objective_future_ids:
            kind = self._label_of(objective, 'objective_type')
            details = [kind, f"atteinte : {objective.achievement}" if objective.achievement else '',
                       objective.description or '', f"commentaire du manager : {objective.manager_comment}"
                       if objective.manager_comment else '']
            objectives.append(f"- {objective.name} : " + ' ; '.join(filter(None, details)))
        add("Objectifs", '\n' + '\n'.join(objectives) if objectives else '')
        competencies = [
            f"- {competency.name} : " + ' ; '.join(filter(None, [
                self._label_of(competency, 'competency_type'), self._label_of(competency, 'level'),
                self._label_of(competency, 'mastery_level'), competency.comment or '']))
            for competency in self.key_competency_ids | self.technical_competency_ids
            | self.soft_skill_competency_ids | self.leadership_competency_ids]
        add("Compétences", '\n' + '\n'.join(competencies) if competencies else '')
        goals = [f"- {goal.name} : " + ' ; '.join(filter(None, [
            self._label_of(goal, 'state'), self._label_of(goal, 'progress'), goal.description or '', goal.notes or '']))
            for goal in self.goal_ids]
        add("Buts", '\n' + '\n'.join(goals) if goals else '')
        return '\n'.join(parts)[:MAX_CONTENT]

    def _label_of(self, record, field_name):
        value = record[field_name]
        if not value:
            return ''
        return dict(record._fields[field_name]._description_selection(self.env)).get(value, value)

    def action_local_ai_summary(self):
        self.ensure_one()
        self.check_access('write')
        content = self._local_ai_summary_content()
        if not content.strip():
            raise UserError(_("The appraisal is empty: fill in the criteria, objectives or comments first."))
        LocalAI = self.env['local.ai']
        answer = LocalAI._chat([{'role': 'user', 'content': SUMMARY_REQUEST.format(content=content)}],
                               system=SUMMARY_SYSTEM, temperature=0.2, max_tokens=700)
        if not answer:
            raise UserError(_("The local AI did not write a summary."))
        self.write({'ai_summary': LocalAI._text_to_html(answer), 'ai_summary_date': fields.Datetime.now()})
        return True
