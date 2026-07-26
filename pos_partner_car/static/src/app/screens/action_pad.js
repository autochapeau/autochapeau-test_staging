/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { ActionpadWidget } from "@point_of_sale/app/screens/product_screen/action_pad/action_pad";

patch(ActionpadWidget.prototype, {
    get selectedVehicleName() {
        const order = this.pos.get_order();
        return order ? order.get_vehicle_name() : "";
    },
});
