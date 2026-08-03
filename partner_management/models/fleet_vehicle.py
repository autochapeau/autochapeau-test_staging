from odoo import _, fields, models
from odoo.exceptions import UserError


class FleetVehicle(models.Model):
    _inherit = "fleet.vehicle"

    sale_order_ids = fields.One2many(
        "sale.order",
        "vehicle_id",
        string="Sale Orders",
    )
    sale_order_count = fields.Integer(
        string="Sale Orders",
        compute="_compute_sale_order_count",
    )

    def _compute_sale_order_count(self):
        for vehicle in self:
            vehicle.sale_order_count = len(vehicle.sale_order_ids)

    def action_create_sale_order(self):
        """Open a Sale Order form with customer + vehicle prefilled."""
        self.ensure_one()
        if not self.partner_id:
            raise UserError(_("Please set an owner on the vehicle first."))
        return {
            "name": _("Sale Order"),
            "type": "ir.actions.act_window",
            "res_model": "sale.order",
            "view_mode": "form",
            "views": [(False, "form")],
            "context": {
                "default_partner_id": self.partner_id.id,
                "default_vehicle_id": self.id,
                "dialog_size": "extra-large",
            },
        }

    def action_view_sale_orders(self):
        """Show every sale order linked to this vehicle."""
        self.ensure_one()
        action = self.env["ir.actions.actions"]._for_xml_id(
            "sale.action_orders"
        )
        action["domain"] = [("vehicle_id", "=", self.id)]
        action["context"] = {
            "default_partner_id": self.partner_id.id,
            "default_vehicle_id": self.id,
        }
        return action
