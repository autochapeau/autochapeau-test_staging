from odoo import _, api, fields, models
from odoo.exceptions import UserError


class CarWorkOrder(models.Model):
    _inherit = "car.work.order"

    is_extern_work_order = fields.Boolean(
        string="Extern Work Order",
        compute="_compute_extern_upsell_info",
    )
    extern_extra_sale_order_count = fields.Integer(
        string="Extern Upsell Orders",
        compute="_compute_extern_upsell_info",
    )

    @api.depends(
        "sale_order_id",
        "sale_order_id.order_type",
        "sale_order_id.child_sale_ids",
    )
    def _compute_extern_upsell_info(self):
        for work_order in self:
            sale = work_order.sudo().sale_order_id
            is_extern = bool(sale and sale.order_type == "extern")
            work_order.is_extern_work_order = is_extern
            work_order.extern_extra_sale_order_count = (
                len(sale.child_sale_ids) if is_extern else 0
            )

    def action_create_extern_upsell_sale_order(self):
        """Create an extra SO for the same customer, linked to this work order visit."""
        self.ensure_one()
        sale = self.sale_order_id
        if not sale or sale.order_type != "extern":
            raise UserError(_(
                "Upsell orders can only be created from an Extern work order."
            ))
        if self.parent_id:
            raise UserError(_(
                "Create the upsell from the main extern work order, "
                "not from a sub work order."
            ))
        if self.state in ("done", "cancelled"):
            raise UserError(_(
                "You cannot create an upsell order on a finished or cancelled "
                "work order."
            ))
        if sale.child_sale_ids:
            raise UserError(_(
                "Only one extra sale order is allowed per Extern order."
            ))
        return sale.action_create_extra_sale_order()

    def action_view_extern_extra_sale_orders(self):
        self.ensure_one()
        if not self.is_extern_work_order:
            raise UserError(_(
                "This work order is not linked to an Extern sale order."
            ))
        return self.sale_order_id.action_view_child_sale_orders()

    def action_create_invoice(self):
        """Invoice extern parent + confirmed upsell (both to the car owner)."""
        self.ensure_one()
        if not self.is_extern_work_order:
            return super().action_create_invoice()

        orders = self.sale_order_id | self.sale_order_id.child_sale_ids
        orders = orders.filtered(lambda order: order.state in ("sale", "done"))
        if not orders:
            return super().action_create_invoice()

        if hasattr(self, "_check_invoice_amount_within_sale_orders"):
            self._check_invoice_amount_within_sale_orders()
        action = self.env["ir.actions.actions"]._for_xml_id(
            "sale.action_view_sale_advance_payment_inv"
        )
        action["context"] = {
            "active_ids": orders.ids,
            "active_id": self.sale_order_id.id,
            "active_model": "sale.order",
        }
        return action

    def action_view_invoices(self):
        """Show invoices of the extern order and its linked upsell order."""
        self.ensure_one()
        if not self.is_extern_work_order:
            return super().action_view_invoices()

        sale_orders = self.sale_order_id | self.sale_order_id.child_sale_ids
        invoices = self.env["account.move"].search([
            ("invoice_origin", "in", sale_orders.mapped("name")),
            ("move_type", "in", ["out_invoice", "out_refund"]),
        ])
        action = self.env.ref("account.action_move_out_invoice_type").read()[0]
        action["views"] = [(False, "list"), (False, "form")]
        action["domain"] = [("id", "in", invoices.ids)] if invoices else [("id", "=", 0)]
        action.pop("res_id", None)
        return action
