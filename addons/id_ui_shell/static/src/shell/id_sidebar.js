import { Component, useEffect, useRef, useState } from "@odoo/owl";
import { useHotkey } from "@web/core/hotkeys/hotkey_hook";
import { useBus, useService } from "@web/core/utils/hooks";
import { ICONS } from "./id_icons";

/**
 * Sidebar daftar aplikasi. Hanya membaca menu lewat service `menu` (API publik);
 * seksi aplikasi tampil sebagai tab di topbar (NavBar bawaan, disesuaikan lewat CSS).
 *
 * Keyboard: Alt+M fokus ke aplikasi, Alt+B ciutkan/bentang, panah atas/bawah pindah
 * aplikasi, Home/End, Enter buka, Esc kembali ke isi. Seksi: Alt+1..9 (bawaan Odoo).
 */
export class IdSidebar extends Component {
    static template = "id_ui_shell.Sidebar";
    static props = {};

    setup() {
        this.menu = useService("menu");
        this.ui = useState(useService("ui"));
        this.shell = useState(useService("id_shell").state);
        this.shellService = useService("id_shell");
        this.root = useRef("root");
        this.icons = ICONS;
        this.state = useState({ appId: this.menu.getCurrentApp()?.id });
        useBus(this.env.bus, "MENUS:APP-CHANGED", () => {
            this.state.appId = this.menu.getCurrentApp()?.id;
        });
        const hotkeyOptions = { global: true, bypassEditableProtection: true };
        useHotkey("alt+m", () => this.focusNav(), hotkeyOptions);
        useHotkey("alt+b", () => this.isActive && this.shellService.toggleCollapsed(), hotkeyOptions);
        useEffect(
            (active, collapsed) => {
                document.body.classList.toggle("id-shell-sidebar", active);
                document.body.classList.toggle("id-shell-collapsed", active && collapsed);
                return () => document.body.classList.remove("id-shell-sidebar", "id-shell-collapsed");
            },
            () => [this.isActive, this.shell.collapsed]
        );
    }

    get isActive() {
        // Di layar kecil dipakai NavBar bawaan (pola mobile menyusul).
        return this.shell.mode === "sidebar" && !this.ui.isSmall;
    }

    get apps() {
        return this.menu.getApps();
    }

    /** Ikon aplikasi bawaan Odoo: gambar (webIconData) atau ikon bentukan (class, warna, latar). */
    iconOf(app) {
        if (app.webIconData) {
            return { src: app.webIconData };
        }
        const [iconClass, color, backgroundColor] = (app.webIcon || "").split(",");
        if (backgroundColor !== undefined) {
            return { iconClass, style: `color:${color};background-color:${backgroundColor}` };
        }
        return { src: "/web/static/img/default_icon_app.png" };
    }

    firstActionMenu(node) {
        if (node.actionID) {
            return node;
        }
        for (const id of node.children || []) {
            const found = this.firstActionMenu(this.menu.getMenu(id));
            if (found) {
                return found;
            }
        }
        return null;
    }

    async openApp(app) {
        this.state.appId = app.id;
        const target = this.firstActionMenu(app);
        if (target) {
            await this.menu.selectMenu(target);
        }
    }

    get navItems() {
        return [...(this.root.el?.querySelectorAll("[data-nav]") || [])];
    }

    focusNav() {
        if (!this.isActive) {
            return;
        }
        const items = this.navItems;
        (items.find((el) => el.classList.contains("is-current")) || items[0])?.focus();
    }

    onKeydown(ev) {
        const items = this.navItems;
        const index = items.indexOf(document.activeElement);
        const key = ev.key;
        if (key === "ArrowDown" || key === "ArrowUp") {
            ev.preventDefault();
            const next = key === "ArrowDown" ? index + 1 : index - 1;
            items[Math.max(0, Math.min(items.length - 1, next))]?.focus();
        } else if (key === "Home" || key === "End") {
            ev.preventDefault();
            items[key === "Home" ? 0 : items.length - 1]?.focus();
        } else if (key === "Escape") {
            ev.preventDefault();
            document.activeElement?.blur();
            document.querySelector(".o_action_manager .o_content, .o_action_manager")?.focus?.();
        }
    }
}
