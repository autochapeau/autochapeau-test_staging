/** @odoo-module **/

import { onWillStart, useSubEnv } from "@odoo/owl";
import { patch } from "@web/core/utils/patch";
import { useService } from "@web/core/utils/hooks";
import { SaleOrderLineProductField } from "@sale/js/sale_product_field";
import {
    ProductConfiguratorDialog
} from "@sale_product_configurator/js/product_configurator_dialog/product_configurator_dialog";
// Loaded first so that its patch on SaleOrderLineProductField stays below ours.
import "@sale_product_configurator/js/sale_product_field";

ProductConfiguratorDialog.props = {
    ...ProductConfiguratorDialog.props,
    vehicleSize: { type: [String, { value: false }], optional: true },
    lockQuantity: { type: Boolean, optional: true },
};

/**
 * Return the Size values allowed for a car size, as
 * {ptalId: {allowed_ids: [], all_ids: []}} per product template.
 */
async function fetchVehicleSizeValues(orm, productTmplIds, vehicleSize) {
    if (!vehicleSize || !productTmplIds.length) return {};
    return orm.call(
        "product.template",
        "get_vehicle_size_ptav_ids",
        [productTmplIds, vehicleSize],
    );
}

patch(SaleOrderLineProductField.prototype, {

    async getProductConfiguratorDialogProps() {
        const props = await super.getProductConfiguratorDialogProps(...arguments);
        const saleOrderRecord = this.props.record.model.root;
        const vehicleId = saleOrderRecord.data.vehicle_id;
        props.vehicleSize = saleOrderRecord.data.vehicle_size || false;
        props.lockQuantity = Boolean(vehicleId && vehicleId[0]);
        if (props.lockQuantity) {
            props.quantity = 1;
        }
        // Preselect the car size before the dialog loads, so that the product name
        // and the price already reflect it.
        const sizeValues = await fetchVehicleSizeValues(
            this.orm, [props.productTemplateId], props.vehicleSize
        );
        const sizeLines = Object.values(sizeValues[props.productTemplateId] || {});
        if (sizeLines.length) {
            const sizeIds = sizeLines.flatMap(line => line.all_ids);
            props.ptavIds = props.ptavIds.filter(ptavId => !sizeIds.includes(ptavId));
            props.ptavIds.push(...sizeLines.map(line => line.allowed_ids[0]));
        }
        return props;
    },
});

patch(ProductConfiguratorDialog.prototype, {

    setup() {
        super.setup(...arguments);
        this.orm = useService("orm");
        this.lockedSizeLineIds = new Set();
        useSubEnv({ lockQuantity: this.props.lockQuantity });
        onWillStart(async () => {
            await this._restrictSizeToVehicle();
        });
    },

    /**
     * Keep only the Size value matching the car, on every loaded product.
     *
     * A service size must follow the car size, so the other values are dropped
     * from the configurator instead of being merely preselected. A line left with
     * a single value is not rendered by the configurator at all.
     */
    async _restrictSizeToVehicle() {
        if (!this.props.vehicleSize) return;
        const products = [...this.state.products, ...this.state.optionalProducts];
        const sizeValues = await fetchVehicleSizeValues(
            this.orm,
            products.map(product => product.product_tmpl_id),
            this.props.vehicleSize,
        );
        let updateNeeded = false;
        for (const product of products) {
            const sizeLines = sizeValues[product.product_tmpl_id];
            if (!sizeLines) continue;
            for (const ptal of product.attribute_lines) {
                const sizeLine = sizeLines[ptal.id];
                if (!sizeLine) continue;
                this.lockedSizeLineIds.add(ptal.id);
                ptal.attribute_values = ptal.attribute_values.filter(
                    ptav => sizeLine.allowed_ids.includes(ptav.id)
                );
                if (!ptal.selected_attribute_value_ids.includes(sizeLine.allowed_ids[0])) {
                    ptal.selected_attribute_value_ids = [sizeLine.allowed_ids[0]];
                    updateNeeded = true;
                }
            }
        }
        if (!updateNeeded) return;
        for (const product of this.state.products) {
            Object.assign(
                product, await this._updateCombination(product, product.quantity)
            );
        }
        this._checkExclusions(this.state.products[0]);
    },

    async _updateProductTemplateSelectedPTAV(productTmplId, ptalId) {
        if (this.lockedSizeLineIds.has(ptalId)) return;
        return super._updateProductTemplateSelectedPTAV(...arguments);
    },

    async _setQuantity(productTmplId, quantity) {
        return super._setQuantity(
            productTmplId, this.props.lockQuantity ? 1 : quantity
        );
    },
});
