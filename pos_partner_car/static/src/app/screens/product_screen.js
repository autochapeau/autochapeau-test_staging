/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { ProductScreen } from "@point_of_sale/app/screens/product_screen/product_screen";

patch(ProductScreen.prototype, {
    async _barcodePartnerAction(code) {
        await super._barcodePartnerAction(...arguments);
        const order = this.currentOrder;
        const partner = order && order.get_partner();
        if (partner) {
            await this.pos.selectPartnerVehicle(order, partner);
        }
    },
});
