/** @odoo-module **/

import { SelectionPopup } from "@point_of_sale/app/utils/input_popups/selection_popup";
import { _t } from "@web/core/l10n/translation";

export class CarSelectionPopup extends SelectionPopup {
    static template = "pos_partner_car.CarSelectionPopup";
    static defaultProps = {
        ...SelectionPopup.defaultProps,
        cancelText: _t("Cancel"),
        newText: _t("New"),
        title: _t("Select Car"),
    };

    createNew() {
        this.props.close({ confirmed: true, payload: { action: "new" } });
    }
}
