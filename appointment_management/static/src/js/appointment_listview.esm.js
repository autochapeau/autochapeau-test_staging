/** @odoo-module **/

import {registry} from "@web/core/registry";
import {listView} from "@web/views/list/list_view";
import {ListRenderer} from "@web/views/list/list_renderer";
import {AppointmentDashBoard} from "@appointment_management/js/appointment_dashboard.esm";

export class AppointmentDashBoardRenderer extends ListRenderer {}

AppointmentDashBoardRenderer.template = "appointment_management.AppointmentListView";
AppointmentDashBoardRenderer.components = Object.assign({}, ListRenderer.components, {AppointmentDashBoard});

export const AppointmentDashBoardListView = {
    ...listView,
    Renderer: AppointmentDashBoardRenderer,
};

registry.category("views").add("appointment_dashboard_list", AppointmentDashBoardListView);
