# -*- coding: utf-8 -*-
from unittest.mock import patch

import requests

from odoo.tests import HttpCase, TransactionCase, new_test_user, tagged

from ..models.local_ai import LocalAIError
from .common import REQUEST, RESOLVE, FakeResponse, configure, fake_ollama


@tagged('post_install', '-at_install')
class TestLocalAI(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        configure(cls.env)
        cls.LocalAI = cls.env['local.ai']

    def test_tailscale_only(self):
        with fake_ollama(['Bonjour'], address='100.127.0.1') as calls:
            self.assertEqual(self.LocalAI._chat([{'role': 'user', 'content': 'Salut'}]), 'Bonjour')
        self.assertEqual(len(calls), 1)
        for address in ('192.168.0.10', '8.8.8.8', '10.0.0.4'):
            with self.subTest(address=address), patch(RESOLVE, return_value=[address]), \
                    patch(REQUEST) as request, self.assertRaisesRegex(LocalAIError, 'outside the Tailscale network'):
                self.LocalAI._chat([{'role': 'user', 'content': 'Salut'}])
            request.assert_not_called()
        # a name resolving to a Tailscale and a LAN address is refused too
        with patch(RESOLVE, return_value=['100.64.0.10', '192.168.0.10']), patch(REQUEST) as request, \
                self.assertRaises(LocalAIError):
            self.LocalAI._chat([{'role': 'user', 'content': 'Salut'}])
        request.assert_not_called()
        with patch(RESOLVE, side_effect=OSError('unknown host')), self.assertRaisesRegex(LocalAIError, 'cannot be found'):
            self.LocalAI._chat([{'role': 'user', 'content': 'Salut'}])
        self.env['ir.config_parameter'].sudo().set_param('local_ai.url', 'ftp://ai.example.ts.net')
        with self.assertRaisesRegex(LocalAIError, 'Invalid address'):
            self.LocalAI._chat([{'role': 'user', 'content': 'Salut'}])
        # explicitly allowed by the system parameter
        configure(self.env)
        self.env['ir.config_parameter'].sudo().set_param('local_ai.tailscale_only', 'False')
        with fake_ollama(['Bonjour'], address='192.168.0.10'):
            self.assertEqual(self.LocalAI._chat([{'role': 'user', 'content': 'Salut'}]), 'Bonjour')

    def test_chat(self):
        with fake_ollama(['<think>raisonnement</think>  Réponse  ']) as calls:
            answer = self.LocalAI._chat([{'role': 'user', 'content': 'Question'}], system='Système',
                                        images=['aW1hZ2U='], num_ctx=8192, max_tokens=50)
        self.assertEqual(answer, 'Réponse')
        payload = calls[0]
        self.assertEqual(payload['model'], 'test-model')
        self.assertIs(payload['stream'], False)
        self.assertIs(payload['think'], False)
        self.assertEqual(payload['messages'][0], {'role': 'system', 'content': 'Système'})
        self.assertEqual(payload['messages'][1]['images'], ['aW1hZ2U='])
        self.assertEqual(payload['options'], {'temperature': 0.2, 'num_ctx': 8192, 'num_predict': 50})
        with fake_ollama(['```json\n{"montant": 12.5}\n```']) as calls:
            self.assertEqual(self.LocalAI._chat_json([{'role': 'user', 'content': 'JSON'}]), {'montant': 12.5})
        self.assertEqual(calls[0]['format'], 'json')
        with fake_ollama(['pas du JSON']), self.assertRaises(LocalAIError):
            self.LocalAI._chat_json([{'role': 'user', 'content': 'JSON'}])

    def test_text_helpers(self):
        html = self.LocalAI._text_to_html("## Titre\nUn **paragraphe** <b>brut</b>.\n\n- point 1\n* point 2\n1. point 3\nFin")
        self.assertEqual(str(html), '<p>Titre</p><p>Un paragraphe &lt;b&gt;brut&lt;/b&gt;.</p>'
                                    '<ul><li>point 1</li><li>point 2</li><li>point 3</li></ul><p>Fin</p>')
        self.assertEqual(self.LocalAI._first_line('\n- « Débogage du parseur »\nautre'), 'Débogage du parseur')

    def test_errors(self):
        message = [{'role': 'user', 'content': 'Question'}]
        with patch(RESOLVE, return_value=['100.64.0.10']):
            with patch(REQUEST, side_effect=requests.Timeout()), self.assertRaisesRegex(LocalAIError, 'did not answer'):
                self.LocalAI._chat(message)
            with patch(REQUEST, side_effect=requests.ConnectionError('refused')), \
                    self.assertRaisesRegex(LocalAIError, 'cannot be reached'):
                self.LocalAI._chat(message)
            with patch(REQUEST, return_value=FakeResponse({'error': 'model not found'}, status=404)), \
                    self.assertRaisesRegex(LocalAIError, 'model not found'):
                self.LocalAI._chat(message)
            with patch(REQUEST, return_value=FakeResponse({'unexpected': True})), \
                    self.assertRaisesRegex(LocalAIError, 'Unexpected answer'):
                self.LocalAI._chat(message)
        self.env['ir.config_parameter'].sudo().set_param('local_ai.url', '')
        self.assertFalse(self.LocalAI._is_enabled())
        with self.assertRaisesRegex(LocalAIError, 'not configured'):
            self.LocalAI._chat(message)

    def test_connection_and_settings(self):
        with fake_ollama(['OK']):
            self.assertIn('test-model', self.LocalAI._test_connection())
        self.env['ir.config_parameter'].sudo().set_param('local_ai.model', 'absent:1b')
        with fake_ollama(['OK']), self.assertRaisesRegex(LocalAIError, 'not installed'):
            self.LocalAI._test_connection()
        self.assertEqual(self.env['res.config.settings'].create({}).local_ai_url, 'http://ai.example.ts.net:11434')

    def test_translation_feature_flag(self):
        values = {}

        class FakeStore:
            def add_global_values(self, **kwargs):
                values.update(kwargs)

            def __getattr__(self, name):
                return lambda *args, **kwargs: None

        user = new_test_user(self.env, login='local_ai_flag_user')
        user.with_user(user)._init_store_data(FakeStore())
        self.assertTrue(values.get('hasMessageTranslationFeature'))
        values.clear()
        self.env['ir.config_parameter'].sudo().set_param('local_ai.url', '')
        user.with_user(user)._init_store_data(FakeStore())
        self.assertFalse(values.get('hasMessageTranslationFeature'))


@tagged('post_install', '-at_install')
class TestLocalAIHttp(HttpCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        configure(cls.env)
        cls.user = new_test_user(cls.env, login='local_ai_user', groups='base.group_user')

    def test_editor_generate_text(self):
        self.authenticate('local_ai_user', 'local_ai_user')
        history = [{'role': 'system', 'content': 'Tu traduis.'}, {'role': 'bogus', 'content': 'ignoré'}]
        with fake_ollama(['<generated_text>Hello</generated_text>']) as calls:
            answer = self.make_jsonrpc_request('/html_editor/generate_text', {
                'prompt': 'Translate <generated_text>Bonjour</generated_text> to English',
                'conversation_history': history,
            })
        self.assertEqual(answer, '<generated_text>Hello</generated_text>')
        roles = [message['role'] for message in calls[0]['messages']]
        self.assertEqual(roles, ['system', 'user'])

    def test_message_translation(self):
        partner = self.env['res.partner'].create({'name': 'Traduction'})
        message = partner.message_post(body='Hello, the prototype is ready.', message_type='comment')
        self.user.lang = 'en_US'
        self.env['res.lang']._activate_lang('fr_FR')
        self.user.lang = 'fr_FR'
        self.authenticate('local_ai_user', 'local_ai_user')
        with fake_ollama(['en', 'Bonjour, le prototype est prêt.']) as calls:
            result = self.make_jsonrpc_request('/mail/message/translate', {'message_id': message.id})
        self.assertIn('Bonjour, le prototype est prêt.', result['body'])
        self.assertEqual(len(calls), 2)
        # the translation is kept: no new request
        with fake_ollama([]) as calls:
            self.make_jsonrpc_request('/mail/message/translate', {'message_id': message.id})
        self.assertFalse(calls)
        # an error of the AI server is returned to the chatter, not raised
        other = partner.message_post(body='Second message', message_type='comment')
        with patch(RESOLVE, return_value=['192.168.0.10']):
            result = self.make_jsonrpc_request('/mail/message/translate', {'message_id': other.id})
        self.assertIn('192.168.0.10', result['error'])  # refused: outside the Tailscale network

    def test_editor_assistant(self):
        """In the browser, the writing assistant joins the editors that have
        the AI translation, and the rewrite dialog replaces the selection
        with the answer of the local AI."""
        code = """
            (async () => {
                const get = (name) => odoo.loader.modules.get(name);
                const errors = [];
                const wait = async (selector) => {
                    for (let i = 0; i < 100; i++) {
                        const element = document.querySelector(selector);
                        if (element) {
                            return element;
                        }
                        await new Promise((resolve) => setTimeout(resolve, 100));
                    }
                    errors.push("not found: " + selector);
                };
                // the web client closes the dialogs when it loads its first action
                await wait(".o_action_manager > *");
                const env = odoo.__WOWL_DEBUG__.root.env;
                const { Editor } = get("@html_editor/editor");
                const { MAIN_PLUGINS } = get("@html_editor/plugin_sets");
                const editable = document.createElement("div");
                document.body.append(editable);
                const editor = new Editor({ Plugins: MAIN_PLUGINS }, env.services);
                editor.attachTo(editable);
                const ids = editor.plugins.map((plugin) => plugin.constructor.id);
                editor.destroy();
                editable.remove();
                for (const id of ["local_ai_writer", "chatgpt_translate"]) {
                    if (!ids.includes(id)) {
                        errors.push("editor without plugin " + id);
                    }
                }
                const { LocalAIRewriteDialog } = get("@local_ai/editor/local_ai_dialogs");
                const { REWRITE_MODES } = get("@local_ai/editor/local_ai_modes");
                let inserted = null;
                env.services.dialog.add(LocalAIRewriteDialog, {
                    originalText: "bonjour le mond",
                    mode: REWRITE_MODES[0],
                    insert: (fragment) => { inserted = fragment.textContent; },
                    sanitize: (node) => node,
                });
                const answer = await wait(".modal [data-message-id]");
                if (answer && !answer.textContent.includes("Bonjour le monde.")) {
                    errors.push("answer: " + answer.textContent);
                }
                const replace = await wait(".modal-footer .btn-primary:not([disabled])");
                replace?.click();
                await new Promise((resolve) => setTimeout(resolve, 200));
                if (inserted !== "Bonjour le monde.") {
                    errors.push("inserted: " + inserted);
                }
                if (errors.length) {
                    console.error(errors.join(" | "));
                } else {
                    console.log("test successful");
                }
            })();
        """
        with fake_ollama(['Bonjour le monde.']) as calls:
            self.browser_js('/odoo', code, ready='odoo.isReady', login='local_ai_user')
        self.assertEqual(len(calls), 1)
        self.assertIn('bonjour le mond', calls[0]['messages'][-1]['content'])
