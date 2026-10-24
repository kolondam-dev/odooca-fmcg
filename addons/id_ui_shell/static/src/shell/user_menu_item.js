import { _t } from "@web/core/l10n/translation";
import { registry } from "@web/core/registry";

// Item menu pengguna: ganti tata letak Sidebar <-> Klasik (per pengguna).
registry.category("user_menuitems").add("id_ui_shell_toggle", (env) => {
    const shell = env.services.id_shell;
    const toSidebar = shell.state.mode !== "sidebar";
    return {
        type: "item",
        id: "id_ui_shell_toggle",
        description: toSidebar ? _t("Layout: switch to Sidebar") : _t("Layout: switch to Classic"),
        callback: () => shell.setMode(toSidebar ? "sidebar" : "classic"),
        sequence: 55,
    };
});
