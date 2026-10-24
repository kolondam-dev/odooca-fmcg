import { Component } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";
import { ICONS } from "./id_icons";

/**
 * Pencarian menu global di topbar: membuka command palette bawaan (awalan "/" = menu).
 * Perhentian Tab pertama halaman: Tab -> sidebar.
 */
export class IdMenuSearch extends Component {
    static template = "id_ui_shell.MenuSearch";
    static props = {};

    setup() {
        this.command = useService("command");
        this.shell = useService("id_shell");
        this.icons = ICONS;
    }

    open() {
        this.command.openMainPalette({ searchValue: "/" });
    }

    onKeydown(ev) {
        if (ev.key === "Tab" && !ev.shiftKey) {
            ev.preventDefault();
            this.shell.focusSidebar();
        }
    }
}
