# -*- coding: utf-8 -*-
from odoo.exceptions import AccessError, UserError
from odoo.tests import TransactionCase, new_test_user, tagged

from odoo.addons.local_ai.tests.common import configure, fake_ollama


@tagged('post_install', '-at_install')
class TestLocalAIAppraisal(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        configure(cls.env)
        cls.employee = cls.env['hr.employee'].create({'name': 'Évalué Test'})
        cls.appraisal = cls.env['hr.appraisal.custom'].create({
            'employee_id': cls.employee.id,
            'strengths': 'Rigueur dans les preuves formelles',
            'areas_improvement': 'Documentation du code',
            'remuneration_notes': 'Augmentation demandée de 10 %',
            'criteria_ids': [(0, 0, {'name': 'Qualité du travail', 'category': 'Technique',
                                     'manager_comment': 'Très bon niveau'})],
            'objective_future_ids': [(0, 0, {'name': 'Publier un article', 'objective_type': 'future'})],
        })

    def test_summary(self):
        content = self.appraisal._local_ai_summary_content()
        self.assertIn('Rigueur dans les preuves formelles', content)
        self.assertIn('Qualité du travail (Technique)', content)
        self.assertIn('Très bon niveau', content)
        self.assertIn('Publier un article', content)
        self.assertNotIn('Augmentation', content, 'remuneration notes are not sent to the AI')
        self.assertNotIn('Évalué Test', content, 'no names')
        answer = ("Synthèse : Bon entretien.\nPoints forts :\n- Rigueur\nAxes de progrès :\n- Documentation\n"
                  "Objectifs à suivre :\n- Publier un article")
        with fake_ollama([answer]) as calls:
            self.appraisal.action_local_ai_summary()
        self.assertEqual(len(calls), 1)
        self.assertIn('<li>Rigueur</li>', self.appraisal.ai_summary)
        self.assertTrue(self.appraisal.ai_summary_date)

    def test_rights_and_errors(self):
        # someone who may not modify the appraisal (record rules of hr_appraisal_custom)
        user = new_test_user(self.env, login='appraisal_reader', groups='base.group_user')
        if not self.appraisal.with_user(user).has_access('write'):
            with fake_ollama([]) as calls, self.assertRaises(AccessError):
                self.appraisal.with_user(user).action_local_ai_summary()
            self.assertFalse(calls)
        empty = self.env['hr.appraisal.custom'].create({'employee_id': self.employee.id})
        empty.job_id = False
        with fake_ollama([]) as calls, self.assertRaises(UserError):
            empty.action_local_ai_summary()
        self.assertFalse(calls)
