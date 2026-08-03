from odoo import _, api, fields, models
from odoo.exceptions import UserError


class CarWorkOrder(models.Model):
    _inherit = "car.work.order"

    is_contract_work_order = fields.Boolean(
        string="Contract Work Order",
        compute="_compute_contract_upsell_info",
    )
    extra_sale_order_ids = fields.One2many(
        related="sale_order_id.child_sale_ids",
        string="Upsell Sale Orders",
        readonly=True,
    )
    extra_sale_order_count = fields.Integer(
        string="Upsell Orders",
        compute="_compute_contract_upsell_info",
    )

    @api.depends(
        "sale_order_id",
        "sale_order_id.order_type",
        "sale_order_id.child_sale_ids",
    )
    def _compute_contract_upsell_info(self):
        for work_order in self:
            sale = work_order.sale_order_id
            is_contract = bool(sale and sale.order_type == "contract")
            work_order.is_contract_work_order = is_contract
            work_order.extra_sale_order_count = (
                len(sale.child_sale_ids) if is_contract else 0
            )

    def action_create_upsell_sale_order(self):
        """Create an extra SO for the car owner, linked to this same work order."""
        self.ensure_one()
        sale = self.sale_order_id
        if not sale or sale.order_type != "contract":
            raise UserError(_(
                "Upsell orders can only be created from a Contract work order."
            ))
        if self.parent_id:
            raise UserError(_(
                "Create the upsell from the main contract work order, "
                "not from a sub work order."
            ))
        if self.state in ("done", "cancelled"):
            raise UserError(_(
                "You cannot create an upsell order on a finished or cancelled "
                "work order."
            ))
        if sale.child_sale_ids:
            raise UserError(_(
                "Only one extra sale order is allowed per Contract order."
            ))
        return sale.action_create_extra_sale_order()

    def action_view_extra_sale_orders(self):
        self.ensure_one()
        if not self.is_contract_work_order:
            raise UserError(_(
                "This work order is not linked to a Contract sale order."
            ))
        return self.sale_order_id.action_view_child_sale_orders()

    def action_create_invoice(self):
        """Invoice contract + confirmed upsell orders together when applicable."""
        self.ensure_one()
        if not self.is_contract_work_order:
            return super().action_create_invoice()

        orders = self.sale_order_id | self.extra_sale_order_ids
        orders = orders.filtered(lambda order: order.state in ("sale", "done"))
        if not orders:
            return super().action_create_invoice()

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
        """Show invoices of the contract order and all linked upsell orders."""
        self.ensure_one()
        if not self.is_contract_work_order:
            return super().action_view_invoices()

        sale_orders = self.sale_order_id | self.extra_sale_order_ids
        invoices = self.env["account.move"].search([
            ("invoice_origin", "in", sale_orders.mapped("name")),
            ("move_type", "in", ["out_invoice", "out_refund"]),
        ])
        action = self.env.ref("account.action_move_out_invoice_type").read()[0]
        action["views"] = [(False, "list"), (False, "form")]
        action["domain"] = [("id", "in", invoices.ids)] if invoices else [("id", "=", 0)]
        action.pop("res_id", None)
        return action
