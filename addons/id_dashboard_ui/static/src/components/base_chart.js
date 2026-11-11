/** @odoo-module **/
import { Component } from "@odoo/owl";
export class Chart extends Component {
    static props = ["*"];
    num(n) {
        return Number.isFinite(n)
            ? new Intl.NumberFormat("id-ID", {
                  maximumFractionDigits: 1,
              }).format(n)
            : "—";
    }
    get height() {
        return `${Number(this.props.height) || 220}px`;
    }
    drill(row) {
        if (row.drill) this.props.onDrill?.(row.drill);
    }
}
