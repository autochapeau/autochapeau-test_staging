/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { Order } from "@point_of_sale/app/store/models";

patch(Order.prototype, {
    setup() {
        super.setup(...arguments);
        this.vehicle = this.vehicle || null;
    },
    init_from_JSON(json) {
        super.init_from_JSON(...arguments);
        if (json.vehicle_id) {
            this.vehicle = {
                id: json.vehicle_id,
                display_name: json.vehicle_name || "",
                license_plate: json.vehicle_license_plate || "",
                size: json.vehicle_size || false,
            };
        } else {
            this.vehicle = null;
        }
    },
    export_as_JSON() {
        const json = super.export_as_JSON(...arguments);
        json.vehicle_id = this.vehicle ? this.vehicle.id : false;
        json.vehicle_name = this.vehicle
            ? this.vehicle.display_name || this.vehicle.license_plate || ""
            : false;
        json.vehicle_license_plate = this.vehicle ? this.vehicle.license_plate || "" : false;
        json.vehicle_size = this.vehicle ? this.vehicle.size || false : false;
        return json;
    },
    set_partner(partner) {
        const previousId = this.partner ? this.partner.id : false;
        super.set_partner(...arguments);
        const newId = partner ? partner.id : false;
        if (previousId !== newId) {
            this.set_vehicle(null);
        }
    },
    set_vehicle(vehicle) {
        this.assert_editable();
        this.vehicle = vehicle || null;
    },
    get_vehicle() {
        return this.vehicle;
    },
    get_vehicle_name() {
        if (!this.vehicle) {
            return "";
        }
        return this.vehicle.display_name || this.vehicle.license_plate || "";
    },
});
