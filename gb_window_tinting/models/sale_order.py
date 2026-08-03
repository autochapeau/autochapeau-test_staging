from odoo import models, _
from odoo.exceptions import ValidationError


class SaleOrder(models.Model):
    _inherit = "sale.order"

    def action_confirm(self):
        for order in self:
            missing_lines = order.order_line.filtered(
                lambda line: (
                    not line.display_type
                    and line.product_id
                    and line.is_window_tinting
                    and not line.tint_detail_ids
                )
            )

            if missing_lines:
                product_names = ", ".join(
                    missing_lines.mapped("product_id.display_name")
                )
                raise ValidationError(
                    _(
                        "Add at least one tint detail before confirming "
                        "the quotation for: %s"
                    )
                    % product_names
                )

        return super().action_confirm()
