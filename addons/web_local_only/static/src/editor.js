import { patch } from "@web/core/utils/patch";
import { session } from "@web/session";
import { Editor } from "@html_editor/editor";
import { MAIN_PLUGINS } from "@html_editor/plugin_sets";
import { ChatGPTTranslatePlugin } from "@html_editor/main/chatgpt/chatgpt_translate_plugin";
import { MediaDialog } from "@html_editor/main/media/media_dialog/media_dialog";
import { ImageSelector } from "@html_editor/main/media/media_dialog/image_selector";

// Local instance: the editor never calls Odoo's online services.

// "Translate" button of the toolbar: ChatGPT through olg.api.odoo.com. It is
// kept when a module answers these requests locally (session.editor_ai_enabled,
// set by local_ai).
patch(Editor.prototype, {
    preparePlugins() {
        if (!session.editor_ai_enabled) {
            const Plugins = (this.config.Plugins || MAIN_PLUGINS).filter((P) => P !== ChatGPTTranslatePlugin);
            this.config = { ...this.config, Plugins };
        }
        return super.preparePlugins(...arguments);
    },
});

// "Illustrations" of the media dialog: media-api.odoo.com.
patch(MediaDialog.prototype, {
    addTab(tab, props) {
        if (props && "useMediaLibrary" in props) {
            props = { ...props, useMediaLibrary: false };
        }
        return super.addTab(tab, props);
    },
});
patch(ImageSelector.prototype, {
    async fetchLibraryMedia() {
        return { media: [], results: null };
    },
});
