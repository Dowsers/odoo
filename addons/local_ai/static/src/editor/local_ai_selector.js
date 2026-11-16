import { Component } from "@odoo/owl";
import { useChildRef } from "@web/core/utils/hooks";
import { Dropdown } from "@web/core/dropdown/dropdown";
import { DropdownItem } from "@web/core/dropdown/dropdown_item";
import { toolbarButtonProps } from "@html_editor/main/toolbar/toolbar";
import { useDropdownAutoVisibility } from "@html_editor/dropdown_autovisibility_hook";
import { REWRITE_MODES } from "./local_ai_modes";

/** Toolbar dropdown: what the AI should do with the selected text. */
export class LocalAIModeSelector extends Component {
    static template = "local_ai.ModeSelector";
    static props = {
        ...toolbarButtonProps,
        onSelected: { type: Function },
    };
    static components = { Dropdown, DropdownItem };

    setup() {
        this.modes = REWRITE_MODES;
        this.menuRef = useChildRef();
        useDropdownAutoVisibility(this.env.overlayState, this.menuRef);
    }
}
