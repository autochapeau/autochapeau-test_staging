/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { PaymentScreen } from "@point_of_sale/app/screens/payment_screen/payment_screen";

patch(PaymentScreen.prototype, {
    async selectPartner(isEditMode = false, missingFields = []) {
        const previousPartner = this.currentOrder.get_partner();
        await super.selectPartner(...arguments);
        const partner = this.currentOrder.get_partner();
        if (partner !== previousPartner) {
            await this.pos.selectPartnerVehicle(this.currentOrder, partner);
        }
    },
});
