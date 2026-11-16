import { _t } from "@web/core/l10n/translation";
import { user } from "@web/core/user";
import { Plugin } from "@html_editor/plugin";
import { isContentEditable } from "@html_editor/utils/dom_info";
import { LocalAIPromptDialog, LocalAIRewriteDialog } from "./local_ai_dialogs";
import { LocalAIModeSelector } from "./local_ai_selector";

/**
 * Writing assistant answered by the local AI server: improve the selected
 * text (toolbar, "ai" group of the ChatGPT translation plugin) and write a
 * text from an instruction ("/AI" command of the powerbox).
 */
export class LocalAIWriterPlugin extends Plugin {
    static id = "local_ai_writer";
    static dependencies = ["baseContainer", "selection", "history", "dom", "sanitize", "dialog", "split"];
    /** @type {import("plugins").EditorResources} */
    resources = {
        toolbar_items: [
            {
                id: "local_ai_rewrite",
                groupId: "ai",
                description: _t("Improve with AI"),
                isAvailable: (selection) => !selection.isCollapsed && user.userId,
                isDisabled: this.isNotReplaceable.bind(this),
                Component: LocalAIModeSelector,
                props: {
                    onSelected: (mode) => this.openRewriteDialog(mode),
                },
            },
        ],
        user_commands: [
            {
                id: "localAiWrite",
                title: _t("AI"),
                description: _t("Write a text with the AI"),
                icon: "fa-magic",
                run: this.openPromptDialog.bind(this),
            },
        ],
        powerbox_items: [
            {
                categoryId: "widget",
                commandId: "localAiWrite",
            },
        ],
    };

    isNotReplaceable(selection = this.dependencies.selection.getEditableSelection()) {
        const isEmpty = !selection.textContent().replace(/\s+/g, "");
        const cannotReplace = this.dependencies.selection
            .getTargetedNodes()
            .find((el) => this.dependencies.split.isUnsplittable(el) || !isContentEditable(el));
        return cannotReplace || isEmpty;
    }

    dialogParams() {
        return {
            insert: (content) => {
                this.dependencies.dom.insert(content);
                this.dependencies.history.addStep();
            },
            sanitize: this.dependencies.sanitize.sanitize,
            baseContainer: this.dependencies.baseContainer.getDefaultNodeName(),
        };
    }

    openRewriteDialog(mode) {
        const selection = this.dependencies.selection.getEditableSelection();
        this.dependencies.dialog.addDialog(LocalAIRewriteDialog, {
            ...this.dialogParams(),
            originalText: selection.textContent() || "",
            mode,
        });
    }

    openPromptDialog() {
        this.dependencies.dialog.addDialog(LocalAIPromptDialog, this.dialogParams());
    }
}
