/** @odoo-module **/
import { Component } from "@odoo/owl";
export class VisualComponent extends Component {
    static props = ["*"];
    get v() {
        return this.renderVals();
    }
    emit(kind, payload = {}) {
        this.props.onEvent?.({ kind, ...payload });
    }
    handleClick(ev) {
        const button = ev.target.closest("button[data-command]");
        if (button) this.emit(button.dataset.command);
    }
}
