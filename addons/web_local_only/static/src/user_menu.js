import { registry } from "@web/core/registry";
// Evaluated first, so that its entries exist when this module runs.
import "@web/webclient/user_menu/user_menu_items";

// Local instance: no "Documentation", "Support" and "My Odoo.com account" entries.
const userMenuItems = registry.category("user_menuitems");
for (const key of ["documentation", "support", "odoo_account"]) {
    if (userMenuItems.contains(key)) {
        userMenuItems.remove(key);
    }
}
