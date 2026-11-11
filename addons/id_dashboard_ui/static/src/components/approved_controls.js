/** @odoo-module **/
import {
  Component,
  onMounted,
  onWillUpdateProps,
  onWillDestroy,
  useRef,
} from "@odoo/owl";
import { mountDashboardControls } from "@id_dashboard_ui/core/controls_controller";
export class ApprovedControls extends Component {
  static template = "id_dashboard_ui.ApprovedControls";
  static props = ["options?", "onApply?"];
  setup() {
    const host = useRef("host");
    let controller;
    const start = (props) => {
      controller?.destroy();
      controller = mountDashboardControls(host.el, {
        ...(props.options || {}),
        onApply: props.onApply,
      });
    };
    onMounted(() => start(this.props));
    onWillUpdateProps((next) => {
      // Data refresh after Apply must not destroy the pending controller or steal focus.
      const identity = (options) => JSON.stringify([options?.dimensions, options?.scopeLabel]);
      if (identity(next.options) !== identity(this.props.options)) start(next);
    });
    onWillDestroy(() => controller?.destroy());
  }
}
