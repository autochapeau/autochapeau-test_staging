/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { ProductsWidget } from "@point_of_sale/app/screens/product_screen/product_list/product_list";

patch(ProductsWidget.prototype, {
    get productsToDisplay() {
        // Depend on token so list refreshes after car selection
        void this.pos.vehicleFilterToken;
        let list = super.productsToDisplay;
        const vehicle = this.pos.get_order()?.get_vehicle();
        const vehicleSize = vehicle && vehicle.size;
        if (!vehicleSize) {
            return list;
        }
        return list.filter((product) => {
            // No Size attribute → always visible
            if (!product.has_size_attribute) {
                return true;
            }
            // Has Size attribute → only matching vehicle size
            const codes = product.size_attribute_codes || [];
            return codes.includes(vehicleSize);
        });
    },
});
