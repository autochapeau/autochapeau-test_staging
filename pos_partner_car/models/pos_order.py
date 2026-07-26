from odoo import api, fields, models


class PosOrder(models.Model):
    _inherit = "pos.order"

    vehicle_id = fields.Many2one(
        "fleet.vehicle",
        string="Car",
        domain="[('partner_id', '=', partner_id)]",
    )

    @api.model
    def _order_fields(self, ui_order):
        fields = super()._order_fields(ui_order)
        fields["vehicle_id"] = ui_order.get("vehicle_id") or False
        return fields

    def _export_for_ui(self, order):
        result = super()._export_for_ui(order)
        result["vehicle_id"] = order.vehicle_id.id if order.vehicle_id else False
        result["vehicle_name"] = order.vehicle_id.display_name if order.vehicle_id else False
        result["vehicle_license_plate"] = (
            order.vehicle_id.license_plate if order.vehicle_id else False
        )
        return result
