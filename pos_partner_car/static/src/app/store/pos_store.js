/** @odoo-module **/

import { _t } from "@web/core/l10n/translation";
import { patch } from "@web/core/utils/patch";
import { PosStore } from "@point_of_sale/app/store/pos_store";
import { ErrorPopup } from "@point_of_sale/app/errors/popups/error_popup";
import { CarSelectionPopup } from "../utils/car_selection_popup";

patch(PosStore.prototype, {
    async selectPartner() {
        const currentOrder = this.get_order();
        if (!currentOrder) {
            return;
        }
        const currentPartner = currentOrder.get_partner();
        if (currentPartner && currentOrder.getHasRefundLines()) {
            this.popup.add(ErrorPopup, {
                title: _t("Can't change customer"),
                body: _t(
                    "This order already has refund lines for %s. We can't change the customer associated to it. Create a new order for the new customer.",
                    currentPartner.name
                ),
            });
            return;
        }
        const { confirmed, payload: newPartner } = await this.showTempScreen("PartnerListScreen", {
            partner: currentPartner,
        });
        if (confirmed) {
            currentOrder.set_partner(newPartner);
            await this.selectPartnerVehicle(currentOrder, newPartner);
        }
    },

    /**
     * Open Cars management in a new browser tab, wait until it is closed,
     * then return control to POS (avoids Owl form errors inside POS UI).
     */
    async openNewPartnerVehicleForm(partner) {
        const url = `/pos_partner_car/new_vehicle?partner_id=${partner.id}`;
        const newWindow = window.open(url, "_blank");
        if (!newWindow) {
            this.popup.add(ErrorPopup, {
                title: _t("Pop-up blocked"),
                body: _t("Please allow pop-ups to create a new car."),
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
    },

    /**
     * Ask cashier to pick one of the partner cars (if any), or create a new one.
     */
    async selectPartnerVehicle(order, partner) {
        if (!order || !partner) {
            if (order) {
                order.set_vehicle(null);
            }
            this.vehicleFilterToken = Date.now();
            return;
        }

        while (true) {
            const vehicles = await this.orm.call("fleet.vehicle", "get_pos_partner_vehicles", [
                partner.id,
            ]);
            const { confirmed, payload } = await this.popup.add(CarSelectionPopup, {
                title: _t("Select Car"),
                emptyText: _t("No cars for this customer"),
                list: vehicles.map((vehicle) => ({
                    id: vehicle.id,
                    label: vehicle.display_name || vehicle.license_plate || String(vehicle.id),
                    isSelected: order.get_vehicle() && order.get_vehicle().id === vehicle.id,
                    item: vehicle,
                })),
            });

            if (!confirmed) {
                if (!order.get_vehicle()) {
                    this.vehicleFilterToken = Date.now();
                }
                return;
            }

            if (payload && payload.action === "new") {
                await this.openNewPartnerVehicleForm(partner);
                continue;
            }

            if (payload) {
                order.set_vehicle(payload);
                this.vehicleFilterToken = Date.now();
            }
            return;
        }
    },
});
