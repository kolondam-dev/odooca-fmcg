import { reactive } from "@odoo/owl";
import { browser } from "@web/core/browser/browser";
import { registry } from "@web/core/registry";
import { user } from "@web/core/user";

const COLLAPSED_KEY = "id_ui_shell.collapsed";
const PANEL_KEY = "id_ui_shell.panel_collapsed";

function readFlag(key) {
    try {
        return browser.localStorage.getItem(key) === "1";
    } catch {
        return false; // penyimpanan tidak tersedia: gunakan bawaan
    }
}

function writeFlag(key, value) {
    try {
        browser.localStorage.setItem(key, value ? "1" : "0");
    } catch {
        // diabaikan
    }
}

const isVisible = (el) => Boolean(el && el.offsetParent !== null);

/**
 * Status shell: mode (sidebar/classic, per pengguna, disimpan di
 * res.users.settings), sidebar ciut dan panel seksi ciut (per peramban), serta
 * pengelola fokus keyboard: pencarian menu -> sidebar -> konten.
 */
export const idShellService = {
    dependencies: [],
    start() {
        const state = reactive({
            mode: user.settings.id_ui_shell || "classic",
            collapsed: readFlag(COLLAPSED_KEY),
            panelCollapsed: readFlag(PANEL_KEY),
        });
        const api = {
            state,
            async setMode(mode) {
                state.mode = mode;
                await user.setUserSettings("id_ui_shell", mode);
            },
            toggleCollapsed() {
                state.collapsed = !state.collapsed;
                writeFlag(COLLAPSED_KEY, state.collapsed);
            },
            togglePanel() {
                state.panelCollapsed = !state.panelCollapsed;
                writeFlag(PANEL_KEY, state.panelCollapsed);
            },
            focusSearch() {
                const el = document.querySelector(".id_menu_search");
                if (isVisible(el)) {
                    el.focus();
                }
            },
            /** Fokus ke aplikasi aktif di sidebar (roving tabindex). */
            focusSidebar() {
                const items = [...document.querySelectorAll(".id_sidebar [data-nav]")];
                const target =
                    items.find((el) => el.getAttribute("tabindex") === "0") ||
                    items.find((el) => el.classList.contains("is-current")) ||
                    items[0];
                target?.focus();
            },
            /** Fokus ke isi: field pertama di form, atau kolom cari di halaman dengan pencarian. */
            focusContent() {
                const root = document.querySelector(".o_action_manager");
                if (!root) {
                    return false;
                }
                const pick = (selector) => [...root.querySelectorAll(selector)].find(isVisible);
                const target =
                    pick(
                        ".o_form_view .o_form_sheet input:not([type=hidden]):not([disabled]):not([readonly]), " +
                            ".o_form_view .o_form_sheet textarea:not([disabled]):not([readonly]), " +
                            ".o_form_view .o_form_sheet select:not([disabled])"
                    ) ||
                    pick(".o_searchview_input") ||
                    pick("button, a[href], input:not([type=hidden]), select, textarea");
                target?.focus();
                return Boolean(target);
            },
            /** Setelah halaman dirender, fokus kembali ke pencarian menu (kecuali ada dialog). */
            focusSearchSoon() {
                browser.setTimeout(() => {
                    if (state.mode === "sidebar" && !document.querySelector(".modal.show, .o_dialog")) {
                        api.focusSearch();
                    }
                }, 150);
            },
        };
        return api;
    },
};

registry.category("services").add("id_shell", idShellService);
