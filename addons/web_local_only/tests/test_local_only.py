# -*- coding: utf-8 -*-
import re
from unittest.mock import patch

from odoo.tests import HttpCase, new_test_user, tagged

from odoo.addons.web_local_only import ODOO_COM_ANCHOR


@tagged('post_install', '-at_install')
class TestLocalOnly(HttpCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.admin = new_test_user(cls.env, login='local_only_admin', groups='base.group_user,base.group_system')

    def test_email_links(self):
        cases = {
            'Powered by <a target="_blank" href="https://www.odoo.com?utm_source=db&amp;utm_medium=auth" style="x">Odoo</a>.':
                'Powered by Odoo.',
            """Powered by <a target="_blank" t-attf-href="https://www.odoo.com?utm_source=db&amp;utm_medium={{ ctx.get('x') }}">Odoo</a>""":
                'Powered by Odoo',
            '<a href="https://www.odoo.com/page/tour?utm_source=db">the Odoo tour</a>': 'the Odoo tour',
        }
        for html, expected in cases.items():
            self.assertEqual(ODOO_COM_ANCHOR.sub(r'\2', html), expected)
        untouched = [
            '<a t-att-href="website_url" t-out="website_url">http://yourcompany.odoo.com</a>',
            '<a href="https://example.com/odoo.com">a link</a>',
        ]
        for html in untouched:
            self.assertEqual(ODOO_COM_ANCHOR.sub(r'\2', html), html)
        linked = self.env['mail.template'].with_context(active_test=False).search([]).filtered(
            lambda template: re.search(r'href=["\']https?://(www\.)?odoo\.com', template.body_html or ''))
        self.assertFalse(linked, 'e-mail templates still linking to odoo.com')

    def test_server_side(self):
        self.assertFalse(self.env.ref('mail.ir_cron_module_update_notification').active)
        self.assertIs(self.env['publisher_warranty.contract'].update_notification(), True)
        self.assertFalse(self.env.ref('base.menu_third_party').active)
        self.assertFalse(self.env.ref('base.menu_theme_store').active)
        self.assertEqual(self.env.ref('base.open_module_tree').domain, "[('to_buy', '=', False)]")
        login_page = self.url_open('/web/login').text
        self.assertNotIn('odoo.com', login_page)
        # the editor's AI never reaches olg.api.odoo.com: refused, or answered locally (local_ai)
        with patch('odoo.addons.html_editor.controllers.main.iap_tools.iap_jsonrpc') as olg:
            self.authenticate('local_only_admin', 'local_only_admin')
            try:
                self.make_jsonrpc_request('/html_editor/generate_text', {'prompt': 'Hello', 'conversation_history': []})
            except Exception:  # noqa: BLE001 - refused (UserError) or local server unavailable
                pass
            olg.assert_not_called()
        self.authenticate('local_only_admin', 'local_only_admin')
        url = self.make_jsonrpc_request('/web/session/account', {})
        self.assertNotIn('odoo.com', url)

    def test_web_client(self):
        """The web client loads without error, the user menu has no odoo.com
        entries, the editor and the templates are patched."""
        code = """
            (async () => {
                const get = (name) => odoo.loader.modules.get(name);
                const errors = [];
                const menu = get("@web/core/registry").registry.category("user_menuitems").getEntries().map(([key]) => key);
                for (const key of ["support", "odoo_account"]) {
                    if (menu.includes(key)) {
                        errors.push("user menu still has " + key);
                    }
                }
                const { getTemplate } = get("@web/core/templates");
                for (const name of ["res_config_edition", "web.InstallScopedApp"]) {
                    const template = getTemplate(name);
                    const xml = new XMLSerializer().serializeToString(template);
                    if (xml.includes("odoo.com")) {
                        errors.push(name + " still links to odoo.com");
                    }
                }
                const { Editor } = get("@html_editor/editor");
                const { MAIN_PLUGINS } = get("@html_editor/plugin_sets");
                const editable = document.createElement("div");
                document.body.append(editable);
                const editor = new Editor({ Plugins: MAIN_PLUGINS }, odoo.__WOWL_DEBUG__.root.env.services);
                editor.attachTo(editable);
                const ids = editor.plugins.map((plugin) => plugin.constructor.id);
                editor.destroy();
                editable.remove();
                // kept only when a module answers the editor's AI locally (local_ai)
                if (ids.includes("chatgpt_translate") !== Boolean(get("@web/session").session.editor_ai_enabled)) {
                    errors.push("ChatGPT plugin: " + ids.includes("chatgpt_translate") +
                        ", local AI enabled: " + Boolean(get("@web/session").session.editor_ai_enabled));
                }
                if (!ids.length) {
                    errors.push("editor started without plugins");
                }
                const { ImageSelector } = get("@html_editor/main/media/media_dialog/image_selector");
                const library = await ImageSelector.prototype.fetchLibraryMedia.call({}, 0);
                if (library.media.length || library.results !== null) {
                    errors.push("media library still queried");
                }
                if (errors.length) {
                    console.error(errors.join(" | "));
                } else {
                    console.log("test successful");
                }
            })();
        """
        self.browser_js('/odoo', code, ready='odoo.isReady', login='local_only_admin')

    def test_settings_page(self):
        code = """
            const start = Date.now();
            const check = () => {
                const rendered = document.querySelector(".o_settings_container") && document.body.textContent.includes("Odoo S.A.");
                if (!rendered) {
                    if (Date.now() - start < 30000) {
                        return setTimeout(check, 250);
                    }
                    return console.error("settings page not rendered");
                }
                const visible = [...document.querySelectorAll('a[href*="odoo.com"]')].filter((a) => a.offsetParent !== null);
                if (visible.length) {
                    console.error("visible odoo.com links: " + visible.map((a) => a.href).join(" "));
                } else {
                    console.log("test successful");
                }
            };
            check();
        """
        self.browser_js('/odoo/settings', code, ready='odoo.isReady', login='local_only_admin')
