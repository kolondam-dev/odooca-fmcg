/** @odoo-module **/
import { Component, useState } from "@odoo/owl";
import * as Primitives from "@id_dashboard_ui/components/ported";
import * as Charts from "@id_dashboard_ui/components/charts";
import { ApprovedControls } from "@id_dashboard_ui/components/approved_controls";
const components = { ...Primitives, ...Charts, ApprovedControls };
class DashboardPage extends Component {
  static props = ["*"];
  static components = components;
  get v() {
    return this.props.data;
  }
}
export class D1 extends DashboardPage {
  static template = "id_dashboard_ui.D1";
}
export class D2 extends DashboardPage {
  static template = "id_dashboard_ui.D2";
}
export class D3 extends DashboardPage {
  static template = "id_dashboard_ui.D3";
}
export class D4 extends DashboardPage {
  static template = "id_dashboard_ui.D4";
}
export class D5 extends DashboardPage {
  static template = "id_dashboard_ui.D5";
}
export class D6 extends DashboardPage {
  static template = "id_dashboard_ui.D6";
}
export class D7 extends DashboardPage {
  static template = "id_dashboard_ui.D7";
}
export const DASHBOARD_PAGES = { D1, D2, D3, D4, D5, D6, D7 };
export class DashboardShell extends Component {
  static template = "id_dashboard_ui.Shell";
  static components = components;
  static props = ["*"];
  get Page() {
    return DASHBOARD_PAGES[this.props.dashboard] || D1;
  }
}
