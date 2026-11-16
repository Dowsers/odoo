import { useState } from "@odoo/owl";
import { ChatGPTDialog } from "@html_editor/main/chatgpt/chatgpt_dialog";
import { REWRITE_SYSTEM, WRITE_SYSTEM } from "./local_ai_modes";

/** Rewrites the selected text according to a mode (correct, rephrase...). */
export class LocalAIRewriteDialog extends ChatGPTDialog {
    static template = "local_ai.RewriteDialog";
    static props = {
        ...ChatGPTDialog.props,
        originalText: String,
        mode: Object,
    };

    setup() {
        super.setup();
        this.state = useState({
            ...this.state,
            conversationHistory: [{ role: "system", content: REWRITE_SYSTEM }],
            messages: [],
            inProgress: true,
        });
        this.run();
    }

    async run() {
        this.state.inProgress = true;
        const query = `${this.props.mode.instruction}\n\nTexte :\n${this.props.originalText}`;
        const messageId = new Date().getTime();
        await this.generate(query, (content, isError) => {
            this.state.inProgress = false;
            this.state.messages = [{ author: "assistant", text: content, id: messageId, isError }];
            this.state.selectedMessageId = messageId;
        });
    }
}

/** Writes a text from an instruction typed by the user ("/AI" command). */
export class LocalAIPromptDialog extends ChatGPTDialog {
    static template = "local_ai.PromptDialog";

    setup() {
        super.setup();
        this.state = useState({
            ...this.state,
            conversationHistory: [{ role: "system", content: WRITE_SYSTEM }],
            messages: [],
            prompt: "",
            inProgress: false,
        });
    }

    onKeydown(ev) {
        if (ev.key === "Enter" && (ev.ctrlKey || ev.metaKey)) {
            ev.preventDefault();
            this.submit();
        }
    }

    async submit() {
        const prompt = this.state.prompt.trim();
        if (!prompt || this.state.inProgress) {
            return;
        }
        this.state.inProgress = true;
        const messageId = new Date().getTime();
        await this.generate(prompt, (content, isError) => {
            this.state.inProgress = false;
            this.state.messages = [{ author: "assistant", text: content, id: messageId, isError }];
            this.state.selectedMessageId = messageId;
        });
    }
}
