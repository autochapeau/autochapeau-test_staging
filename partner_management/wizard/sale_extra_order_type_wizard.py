from odoo import _, fields, models
from odoo.exceptions import UserError


class SaleExtraOrderTypeWizard(models.TransientModel):
    _name = "sale.extra.order.type.wizard"
    _description = "Choose Extra Sale Order Type"

    sale_order_id = fields.Many2one(
        "sale.order",
        required=True,
        readonly=True,
    )
    order_type = fields.Selection(
        [
            ("intern", "Intern"),
            ("extern", "Extern"),
        ],
        string="Extra Order Type",
        required=True,
        default="intern",
    )

    def action_continue(self):
        """Continue to OTP (if needed) or create the Extra Order."""
        self.ensure_one()
        order = self.sale_order_id
        if not order:
            raise UserError(_("Missing contract sale order."))
        return order.with_context(
            skip_extra_order_type_wizard=True,
            extra_order_type=self.order_type,
        ).action_create_extra_sale_order()
