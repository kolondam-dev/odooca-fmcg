import { Component, useEffect, useRef, useState } from "@odoo/owl";
import { useHotkey } from "@web/core/hotkeys/hotkey_hook";
import { _t } from "@web/core/l10n/translation";
import { useBus, useService } from "@web/core/utils/hooks";
import { ICONS } from "./id_icons";

/**
 * Panel seksi (sidebar dalam): seksi > sub-seksi > sub, di kiri konten. Menggantikan
 * tab seksi di NavBar. Membaca menu lewat service `menu`; menu aktif dikenali dari
 * action yang sedang tampil (`action.currentController`).
 *
 * Keyboard: dimasuki dari sidebar dengan panah kanan; panah atas/bawah pindah item,
 * panah kanan/kiri buka/tutup grup (kiri pada item = kembali ke sidebar), Tab ke isi,
 * Shift+Tab ke sidebar, Alt+P ciutkan/bentang panel.
 */
export class IdSectionPanel extends Component {
    static template = "id_ui_shell.SectionPanel";
    static props = {};

    setup() {
        this.menu = useService("menu");
        this.action = useService("action");
        this.ui = useState(useService("ui"));
        this.shell = useState(useService("id_shell").state);
        this.shellService = useService("id_shell");
        this.root = useRef("root");
        this.icons = ICONS;
        this.state = useState({ appId: this.menu.getCurrentApp()?.id, activeId: null, open: {} });
        const refresh = () => {
            this.state.appId = this.menu.getCurrentApp()?.id;
            this.syncActive();
        };
        useBus(this.env.bus, "MENUS:APP-CHANGED", refresh);
        useBus(this.env.bus, "ACTION_MANAGER:UI-UPDATED", refresh);
        useHotkey("alt+p", () => this.visible && this.shellService.togglePanel(), {
            global: true,
            bypassEditableProtection: true,
        });
        useEffect(
            (visible, collapsed) => {
                document.body.classList.toggle("id-shell-panel", visible);
                document.body.classList.toggle("id-shell-panel-collapsed", visible && collapsed);
                return () => document.body.classList.remove("id-shell-panel", "id-shell-panel-collapsed");
            },
            () => [this.visible, this.shell.panelCollapsed]
        );
    }

    get isActive() {
        return this.shell.mode === "sidebar" && !this.ui.isSmall;
    }

    get tree() {
        // Membaca state.appId (reaktif) agar panel dirender ulang saat aplikasi berganti.
        const appId = this.state.appId;
        return appId ? this.menu.getMenuAsTree(appId).childrenTree || [] : [];
    }

    get visible() {
        return this.isActive && this.tree.length > 0;
    }

    get toggleTitle() {
        return this.shell.panelCollapsed ? _t("Expand panel (Alt+P)") : _t("Collapse panel (Alt+P)");
    }

    get toggleIcon() {
        return this.shell.panelCollapsed ? this.icons.chevronsRight : this.icons.chevronsLeft;
    }

    findByAction(nodes, actionId) {
        for (const node of nodes) {
            if (node.actionID && node.actionID === actionId) {
                return node;
            }
            const found = this.findByAction(node.childrenTree || [], actionId);
            if (found) {
                return found;
            }
        }
        return null;
    }

    syncActive() {
        const actionId = this.action.currentController?.action?.id;
        const node = actionId ? this.findByAction(this.tree, actionId) : null;
        if (node) {
            this.state.activeId = node.id;
        }
    }

    /** Seksi tingkat 1 terbuka; sub-seksi tertutup kecuali dilalui menu aktif. */
    isOpen(node, depth) {
        const explicit = this.state.open[node.id];
        if (explicit !== undefined) {
            return explicit;
        }
        return depth === 0 || this.containsActive(node);
    }

    containsActive(node) {
        return (node.childrenTree || []).some(
            (child) => child.id === this.state.activeId || this.containsActive(child)
        );
    }

    toggleGroup(node, depth) {
        this.state.open[node.id] = !this.isOpen(node, depth);
    }

    async openMenu(node) {
        this.state.activeId = node.id;
        await this.menu.selectMenu(node);
    }

    get navItems() {
        return [...(this.root.el?.querySelectorAll("[data-panel-nav]") || [])];
    }

    onKeydown(ev) {
        const items = this.navItems;
        const index = items.indexOf(document.activeElement);
        const key = ev.key;
        const el = document.activeElement;
        const groupId = Number(el?.dataset.groupId);
        if (key === "Tab") {
            ev.preventDefault();
            if (ev.shiftKey) {
                this.shellService.focusSidebar();
            } else {
                this.shellService.focusContent();
            }
        } else if (key === "ArrowDown" || key === "ArrowUp") {
            ev.preventDefault();
            const next = key === "ArrowDown" ? index + 1 : index - 1;
            items[Math.max(0, Math.min(items.length - 1, next))]?.focus();
        } else if (key === "Home" || key === "End") {
            ev.preventDefault();
            items[key === "Home" ? 0 : items.length - 1]?.focus();
        } else if (key === "ArrowRight" && groupId && el.getAttribute("aria-expanded") === "false") {
            ev.preventDefault();
            this.state.open[groupId] = true;
        } else if (key === "ArrowLeft") {
            ev.preventDefault();
            if (groupId && el.getAttribute("aria-expanded") === "true") {
                this.state.open[groupId] = false;
            } else {
                this.shellService.focusSidebar();
            }
        } else if (key === "Escape") {
            ev.preventDefault();
            this.shellService.focusContent();
        }
    }
}
