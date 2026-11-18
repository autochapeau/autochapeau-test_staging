/** @odoo-module **/

import { _t } from "@web/core/l10n/translation";
import { ConnectionLostError } from "@web/core/network/rpc_service";
import { registry } from "@web/core/registry";
import { FileUploader } from "@web/views/fields/file_handler";
import {
    Many2ManyBinaryField,
    many2ManyBinaryField,
} from "@web/views/fields/many2many_binary/many2many_binary_field";

export class PaymentProofField extends Many2ManyBinaryField {
    static template = "sale_split_payment.PaymentProofField";
    static components = { FileUploader };

    async onProofUploaded({ name, size, data }) {
        if (!size) {
            this.notification.add(_t("Select a payment attachment that is not empty."), {
                type: "warning",
            });
            return;
        }

        const { resModel, resId } = this.props.record;
        let attachmentId;
        try {
            [attachmentId] = await this.orm.create("ir.attachment", [{
                name,
                datas: data,
                res_model: resModel,
                res_id: resId || 0,
            }]);
        } catch (error) {
            if (!(error instanceof ConnectionLostError)) {
                throw error;
            }
            this.notification.add(
                _t("The server did not accept the payment attachment. Check your connection or try a smaller file."),
                { type: "danger" }
            );
            return;
        }
        await this.onFileUploaded([{ id: attachmentId }]);
    }
}

registry.category("fields").add("payment_proof", {
    ...many2ManyBinaryField,
    component: PaymentProofField,
});
