import { patch } from "@web/core/utils/patch";
import { session } from "@web/session";
import { Editor } from "@html_editor/editor";
import { MAIN_PLUGINS } from "@html_editor/plugin_sets";
import { ChatGPTTranslatePlugin } from "@html_editor/main/chatgpt/chatgpt_translate_plugin";
import { LocalAIWriterPlugin } from "./local_ai_writer_plugin";

// The writing assistant joins the editors that have Odoo's AI translation
// (rich text fields, mail composer), when the local AI is configured.
patch(Editor.prototype, {
    preparePlugins() {
        if (session.editor_ai_enabled) {
            const Plugins = this.config.Plugins || MAIN_PLUGINS;
            if (Plugins.includes(ChatGPTTranslatePlugin) && !Plugins.includes(LocalAIWriterPlugin)) {
                this.config = { ...this.config, Plugins: [...Plugins, LocalAIWriterPlugin] };
            }
        }
        return super.preparePlugins(...arguments);
    },
});
