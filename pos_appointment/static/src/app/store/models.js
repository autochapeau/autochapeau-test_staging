/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { Order } from "@point_of_sale/app/store/models";

patch(Order.prototype, {
    setup() {
        super.setup(...arguments);
        this.appointment_id = this.appointment_id || false;
        this.appointment_name = this.appointment_name || "";
    },
    init_from_JSON(json) {
        super.init_from_JSON(...arguments);
        this.appointment_id = json.appointment_id || false;
        this.appointment_name = json.appointment_name || "";
    },
    export_as_JSON() {
        const json = super.export_as_JSON(...arguments);
        json.appointment_id = this.appointment_id || false;
        json.appointment_name = this.appointment_name || false;
        return json;
    },
    set_appointment(appointment) {
        if (!appointment) {
            this.appointment_id = false;
            this.appointment_name = "";
            return;
        }
        this.appointment_id = appointment.id || false;
        this.appointment_name = appointment.name || "";
    },
    get_appointment_id() {
        return this.appointment_id || false;
    },
});
