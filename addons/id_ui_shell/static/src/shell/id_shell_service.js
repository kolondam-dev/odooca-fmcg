import { reactive } from "@odoo/owl";
import { browser } from "@web/core/browser/browser";
import { registry } from "@web/core/registry";
import { user } from "@web/core/user";

const COLLAPSED_KEY = "id_ui_shell.collapsed";

/**
 * Status shell: mode (sidebar/classic, per pengguna, disimpan di
 * res.users.settings) dan sidebar tersembunyi/terbuka (per peramban).
 */
export const idShellService = {
    dependencies: [],
    start() {
        let collapsed = false;
        try {
            collapsed = browser.localStorage.getItem(COLLAPSED_KEY) === "1";
        } catch {
            // penyimpanan tidak tersedia: gunakan bawaan
        }
        const state = reactive({
            mode: user.settings.id_ui_shell || "classic",
            collapsed,
        });
        return {
            state,
            async setMode(mode) {
                state.mode = mode;
                await user.setUserSettings("id_ui_shell", mode);
            },
            toggleCollapsed() {
                state.collapsed = !state.collapsed;
                try {
                    browser.localStorage.setItem(COLLAPSED_KEY, state.collapsed ? "1" : "0");
                } catch {
                    // diabaikan
                }
            },
        };
    },
};

registry.category("services").add("id_shell", idShellService);
