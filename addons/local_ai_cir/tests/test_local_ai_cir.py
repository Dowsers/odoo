# -*- coding: utf-8 -*-
from datetime import date
from unittest.mock import patch

from odoo.exceptions import AccessError, UserError
from odoo.tests import TransactionCase, new_test_user, tagged

from odoo.addons.local_ai.tests.common import configure, fake_ollama

YEAR = 2031


@tagged('post_install', '-at_install')
class TestLocalAICir(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env = cls.env(context=dict(cls.env.context, tracking_disable=True))
        configure(cls.env)
        cls.company = cls.env.company
        cls.company.timesheet_encode_uom_id = cls.env.ref('uom.product_uom_day')
        cls.calendar = cls.env['resource.calendar'].create({
            'name': 'CIR 40h', 'hours_per_day': 8.0, 'tz': 'Europe/Paris', 'company_id': cls.company.id})
        cls.user = new_test_user(cls.env, login='cir_user', groups='base.group_user,hr_timesheet.group_hr_timesheet_user')
        cls.other_user = new_test_user(cls.env, login='cir_other', groups='base.group_user,hr_timesheet.group_hr_timesheet_user')
        cls.admin = new_test_user(cls.env, login='cir_admin',
                                  groups='base.group_user,hr_timesheet.group_timesheet_manager,project.group_project_user')
        Employee = cls.env['hr.employee']
        cls.employee = Employee.create({'name': 'Chercheur Test', 'user_id': cls.user.id,
                                        'resource_calendar_id': cls.calendar.id})
        cls.other_employee = Employee.create({'name': 'Collègue Test', 'user_id': cls.other_user.id,
                                              'resource_calendar_id': cls.calendar.id})
        plan = cls.env['account.analytic.plan'].create({'name': 'CIR plan'})
        cls.project = cls.env['project.project'].create({
            'name': 'Recherche Test', 'allow_timesheets': True, 'privacy_visibility': 'employees',
            'account_id': cls.env['account.analytic.account'].create({'name': 'Recherche Test', 'plan_id': plan.id}).id})
        Task = cls.env['project.task']
        cls.task = Task.create({'name': 'Prouveur Test', 'project_id': cls.project.id,
                                'description': '<p>Prouveur de contrats intelligents.</p>'})
        cls.empty_task = Task.create({'name': 'Tâche Vide', 'project_id': cls.project.id})
        cls.leave_task = Task.create({'name': 'Congés', 'project_id': cls.project.id})
        cls.Line = cls.env['account.analytic.line']

    def _log(self, day, name, task=None, employee=None, hours=8):
        return self.Line.create({'name': name, 'date': day, 'unit_amount': hours, 'project_id': self.project.id,
                                 'task_id': (task or self.task).id, 'employee_id': (employee or self.employee).id})

    def test_description_quality(self):
        self.assertTrue(self.leave_task.timesheet_absence)
        cases = {
            '/': 'missing', '  ': 'missing', 'Fix': 'short', 'Tests unitaires': 'short',
            'Débogage du parseur Boogie sur les mappings imbriqués': 'ok',
        }
        for day, (name, quality) in enumerate(cases.items(), start=2):
            with self.subTest(name=name):
                self.assertEqual(self._log(date(YEAR, 3, day), name).cir_description_quality, quality)
        self.assertFalse(self._log(date(YEAR, 3, 10), '/', task=self.leave_task).cir_description_quality)
        line = self._log(date(YEAR, 3, 11), '/')
        line.name = 'Mise en place de la génération des invariants de boucle'
        self.assertEqual(line.cir_description_quality, 'ok')

    def test_suggestions(self):
        self._log(date(YEAR, 3, 2), 'Débogage du parseur Boogie sur les mappings imbriqués')
        self._log(date(YEAR, 3, 3), 'Revue des preuves de terminaison avec l équipe', employee=self.other_employee)
        line = self._log(date(YEAR, 3, 4), '/')
        others = self._log(date(YEAR, 3, 5), '/', employee=self.other_employee)
        with self.assertRaises(AccessError):
            (line | others).with_user(self.user).action_local_ai_suggest()
        line.with_user(self.user).action_local_ai_suggest()
        self.assertEqual(line.ai_state, 'queued')
        prompts = []

        def answer(payload):
            prompts.append(payload['messages'][-1]['content'])
            return '- « Débogage du parseur Boogie »'

        with fake_ollama([answer]), patch.object(type(self.env['ir.cron']), '_commit_progress',
                                                 return_value=float('inf')):
            self.env['local.ai']._cron_process_queue()
        self.assertEqual((line.ai_state, line.ai_suggestion), ('done', 'Débogage du parseur Boogie'))
        self.assertIn('Débogage du parseur Boogie sur les mappings imbriqués', prompts[0])
        self.assertIn('Revue des preuves de terminaison', prompts[0])
        self.assertIn('Prouveur de contrats intelligents', prompts[0])
        line.with_user(self.user).action_local_ai_apply()
        self.assertEqual((line.name, line.ai_suggestion, line.ai_state), ('Débogage du parseur Boogie', False, False))
        self.assertEqual(line.cir_description_quality, 'ok')
        with self.assertRaises(UserError):
            line.with_user(self.user).action_local_ai_suggest()

    def test_suggestion_error(self):
        line = self._log(date(YEAR, 3, 4), '/')
        line._local_ai_enqueue()
        with fake_ollama([''], address='192.168.0.10'):
            line._local_ai_run()
        self.assertEqual(line.ai_state, 'error')
        self.assertIn('Tailscale', line.ai_error)

    def test_clean_section(self):
        Draft = self.env['local.ai.cir.draft']
        instruction = "Rédige la section « Travaux réalisés » : 3 à 8 puces"
        for answer, expected in [
            ("Voici le contenu de la section « Travaux réalisés » basé sur les informations fournies :\n- A\n- B", "- A\n- B"),
            ("Travaux réalisés\n- A", "- A"),
            ("## Travaux réalisés :\n\n- A", "- A"),
            ("Travaux réalisés : développement du parseur.", "développement du parseur."),
            ("- Voici un travail : A", "- Voici un travail : A"),
        ]:
            self.assertEqual(Draft._clean_section(answer, instruction), expected, answer)

    def test_drafts(self):
        self._log(date(YEAR, 1, 15), 'Débogage du parseur Boogie sur les mappings imbriqués')
        self._log(date(YEAR, 2, 3), 'Génération des invariants de boucle pour les contrats', employee=self.other_employee)
        self._log(date(YEAR, 2, 4), '/', hours=4)
        for day, text in [(10, 'Spécification du langage intermédiaire'), (11, 'Traduction des boucles for'),
                          (12, 'Tests sur les contrats ERC20')]:
            self._log(date(YEAR, 2, day), text, hours=2)
        self._log(date(YEAR, 2, 5), '/', task=self.empty_task)
        self._log(date(YEAR, 2, 6), '/', task=self.leave_task)
        wizard = self.env['local.ai.cir.draft.wizard'].with_user(self.admin).create({'year': str(YEAR)})
        self.assertEqual(wizard.task_ids, self.task | self.empty_task, 'absence tasks are left out')
        action = wizard.action_generate()
        drafts = self.env['local.ai.cir.draft'].search(action['domain'])
        self.assertEqual(drafts.task_id, self.task | self.empty_task)
        self.assertEqual(set(drafts.mapped('ai_state')), {'queued'})
        draft = drafts.filtered(lambda draft: draft.task_id == self.task)
        answers = ['- Débogage du parseur\n- Génération des invariants',
                   "Voici la section demandée :\n**Objectifs de l'opération**\nObjectif : un prouveur.",
                   '- Verrou : invariants de boucle', '- Débogage\n- Invariants', 'À compléter : préciser les résultats obtenus.']
        with fake_ollama(answers) as calls:
            draft._local_ai_run()
        self.assertEqual(draft.ai_state, 'done', draft.ai_error)
        self.assertEqual(len(calls), 5, 'one summary and four sections')
        self.assertIn('Débogage du parseur Boogie', calls[0]['messages'][-1]['content'])
        self.assertIn('<li>Verrou : invariants de boucle</li>', draft.obstacles)
        self.assertEqual(draft.objectives, '<p>Objectif : un prouveur.</p>', 'introduction and title removed')
        self.assertEqual((draft.total_days, draft.employee_count, draft.line_count, draft.described_count), (3.25, 2, 6, 5))
        self.assertIn('Chercheur Test', draft.facts)
        self.assertEqual(draft.model_used, 'test-model')
        empty = drafts - draft
        with fake_ollama([]) as calls:
            empty._local_ai_run()
        self.assertFalse(calls, 'no description: nothing is asked to the AI')
        self.assertIn('À compléter', empty.work)
        # a single described timesheet: too thin, the AI is not asked, the entry is kept
        thin_task = self.env['project.task'].create({'name': 'Tâche Peu Décrite', 'project_id': self.project.id})
        self._log(date(YEAR, 3, 2), 'Lecture de la spécification Boogie', task=thin_task)
        thin = self.env['local.ai.cir.draft'].create({'year': YEAR, 'task_id': thin_task.id})
        with fake_ollama([]) as calls:
            thin._local_ai_run()
        self.assertFalse(calls, 'too little material: nothing is asked to the AI')
        self.assertIn('trop peu de matière', thin.work)
        self.assertIn('Lecture de la spécification Boogie', thin.work)
        self.assertFalse(thin.model_used)
        html, _format = self.env['ir.actions.report']._render_qweb_html('local_ai_cir.report_cir_draft', drafts.ids)
        self.assertIn(b'Prouveur Test', html)
        self.assertIn(b'Verrou : invariants de boucle', html)
        with self.assertRaises(UserError):
            draft.with_user(self.user).action_generate()
        with self.assertRaises(AccessError):
            self.env['local.ai.cir.draft'].with_user(self.user).search([])
