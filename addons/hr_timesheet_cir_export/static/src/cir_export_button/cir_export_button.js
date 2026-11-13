import { Component, onWillDestroy, useState } from "@odoo/owl";
import { _t } from "@web/core/l10n/translation";
import { download } from "@web/core/network/download";
import { useService } from "@web/core/utils/hooks";
import { ControlPanel } from "@web/search/control_panel/control_panel";

// actionId -> Promise<boolean>, shared by every control panel of the session
const visibilityCache = new Map();

/**
 * Download button shown in the control panel of the "All Timesheets" action
 * (every view type) to timesheet administrators. One click downloads the ZIP
 * of the CIR timesheets of the current year, stopped at the previous
 * complete month.
 */
export class TimesheetCirExportButton extends Component {
    static template = "hr_timesheet_cir_export.ControlPanelButton";
    static props = {};

    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.state = useState({ visible: false, busy: false });
        this.destroyed = false;
        onWillDestroy(() => {
            this.destroyed = true;
        });
        const actionId = this.env.config && this.env.config.actionId;
        if (actionId) {
            this.getVisibility(actionId).then((visible) => {
                if (!this.destroyed) {
                    this.state.visible = visible;
                }
            });
        }
    }

    getVisibility(actionId) {
        if (!visibilityCache.has(actionId)) {
            const promise = this.orm
                .call("hr.timesheet.cir.export.wizard", "is_export_button_visible", [actionId])
                .then((result) => Boolean(result))
                .catch(() => false);
            visibilityCache.set(actionId, promise);
        }
        return visibilityCache.get(actionId);
    }

    async onClick() {
        if (this.state.busy) {
            return;
        }
        this.state.busy = true;
        try {
            await download({ url: "/hr_timesheet_cir_export/download", data: {} });
        } catch (error) {
            const message = (error.data && error.data.message) || error.message || "";
            this.notification.add(message || _t("The export failed."), {
                title: _t("CIR Export (ZIP)"),
                type: "danger",
            });
        } finally {
            if (!this.destroyed) {
                this.state.busy = false;
            }
        }
    }
}

ControlPanel.components = { ...ControlPanel.components, TimesheetCirExportButton };
