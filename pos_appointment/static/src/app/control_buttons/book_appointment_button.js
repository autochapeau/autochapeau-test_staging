/** @odoo-module **/

import { _t } from "@web/core/l10n/translation";
import { usePos } from "@point_of_sale/app/store/pos_hook";
import { useService } from "@web/core/utils/hooks";
import { ProductScreen } from "@point_of_sale/app/screens/product_screen/product_screen";
import { Component } from "@odoo/owl";
import { ErrorPopup } from "@point_of_sale/app/errors/popups/error_popup";

export class BookAppointmentButton extends Component {
    static template = "pos_appointment.BookAppointmentButton";

    setup() {
        this.pos = usePos();
        this.popup = useService("popup");
        this.orm = useService("orm");
    }

    async click() {
        const order = this.pos.get_order();
        if (!order) {
            return;
        }
        const partner = order.get_partner();
        const vehicle = order.get_vehicle && order.get_vehicle();

        if (!partner) {
            await this.popup.add(ErrorPopup, {
                title: _t("Customer required"),
                body: _t("Please select a customer before booking an appointment."),
            });
            return;
        }
        if (!vehicle) {
            await this.popup.add(ErrorPopup, {
                title: _t("Car required"),
                body: _t("Please select a car before booking an appointment."),
            });
            return;
        }

        // If already linked, open existing appointment
        if (order.get_appointment_id()) {
            const url = `/web#id=${order.get_appointment_id()}&model=car.appointment&view_type=form`;
            window.open(url, "_blank");
            return;
        }

        const posUid = order.name || order.uid || "";
        const posOrderId = order.server_id || 0;
        const url =
            `/pos_appointment/new` +
            `?partner_id=${partner.id}` +
            `&vehicle_id=${vehicle.id}` +
            `&pos_uid=${encodeURIComponent(posUid)}` +
            `&pos_order_id=${posOrderId}`;

        const newWindow = window.open(url, "_blank");
        if (!newWindow) {
            await this.popup.add(ErrorPopup, {
                title: _t("Pop-up blocked"),
                body: _t("Please allow pop-ups to book an appointment."),
            });
            return;
        }

        await new Promise((resolve) => {
            const timer = window.setInterval(() => {
                if (newWindow.closed) {
                    window.clearInterval(timer);
                    resolve();
                }
            }, 500);
        });

        const appointment = await this.orm.call(
            "car.appointment",
            "get_appointment_for_pos_uid",
            [posUid]
        );
        if (appointment) {
            order.set_appointment(appointment);
        }
    }
}

ProductScreen.addControlButton({
    component: BookAppointmentButton,
    condition: function () {
        return true;
    },
});
