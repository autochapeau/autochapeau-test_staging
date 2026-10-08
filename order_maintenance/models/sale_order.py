from odoo import _, api, fields, models
from odoo.exceptions import UserError


class SaleOrder(models.Model):
    _inherit = "sale.order"

    maintenance_claim_id = fields.Many2one(
        "maintenance.claim",
        string="Maintenance Request",
        copy=False,
        index=True,
        readonly=True,
    )
    maintenance_claim_ids = fields.One2many(
        "maintenance.claim",
        "origin_sale_id",
        string="Maintenance Requests",
    )
    maintenance_claim_count = fields.Integer(
        compute="_compute_maintenance_claim_count",
    )

    @api.depends("maintenance_claim_ids")
    def _compute_maintenance_claim_count(self):
        for order in self:
            order.maintenance_claim_count = len(order.maintenance_claim_ids)

    def action_open_maintenance_wizard(self):
        self.ensure_one()
        if not (
            self.env.user.has_group("sales_team.group_sale_salesman")
            or self.env.user.has_group("work_orders.group_workshop_manager")
            or self.env.user.has_group("work_orders.group_quality_officer")
        ):
            raise UserError(_("You are not allowed to create a maintenance request."))
        if self.state not in ("sale", "done"):
            raise UserError(_("Maintenance can be requested from a confirmed order."))
        if not self.vehicle_id:
            raise UserError(_("Select a car on the order before requesting maintenance."))
        if not self.has_service_product_lines:
            raise UserError(_("This order has no service to maintain."))
        return {
            "type": "ir.actions.act_window",
            "name": _("Maintenance Request"),
            "res_model": "maintenance.claim.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {"default_sale_order_id": self.id},
        }

    def action_view_maintenance_claims(self):
        self.ensure_one()
        action = self.env["ir.actions.act_window"]._for_xml_id(
            "order_maintenance.maintenance_claim_action"
        )
        action["domain"] = [("origin_sale_id", "=", self.id)]
        if self.maintenance_claim_count == 1:
            action.update({
                "views": [(False, "form")],
                "res_id": self.maintenance_claim_ids.id,
            })
        return action


class SaleOrderLine(models.Model):
    _inherit = "sale.order.line"

    def _is_non_customer_maintenance(self):
        self.ensure_one()
        claim = self.order_id.maintenance_claim_id
        return bool(claim and claim.fault_type in ("technician", "supplier"))

    def _get_display_price(self):
        """Technician and supplier faults are free for the customer."""
        self.ensure_one()
        if self._is_non_customer_maintenance():
            return 0.0
        return super()._get_display_price()

    @api.depends(
        "product_id",
        "product_uom",
        "product_uom_qty",
        "order_id.maintenance_claim_id.fault_type",
    )
    def _compute_discount(self):
        super()._compute_discount()
        for line in self:
            if line._is_non_customer_maintenance():
                line.discount = 0.0
