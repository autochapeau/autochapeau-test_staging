/** @odoo-module **/

import {registry} from "@web/core/registry";
import {listView} from "@web/views/list/list_view";
import {ListRenderer} from "@web/views/list/list_renderer";
import {WorkOrderDashBoard} from "@work_orders/js/workorder_dashboard.esm";

export class WorkOrderDashBoardRenderer extends ListRenderer {}

WorkOrderDashBoardRenderer.template = "work_orders.WorkOrderListView";
WorkOrderDashBoardRenderer.components = Object.assign({}, ListRenderer.components, {WorkOrderDashBoard});

export const WorkOrderDashBoardListView = {
    ...listView,
    Renderer: WorkOrderDashBoardRenderer,
};

registry.category("views").add("workorder_dashboard_list", WorkOrderDashBoardListView);
