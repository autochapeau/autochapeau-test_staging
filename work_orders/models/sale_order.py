from odoo import api, fields, models


class SaleOrder(models.Model):
    _inherit = "sale.order"

    order_state = fields.Selection(
        compute="_compute_order_state",
        selection=[
            ("new", "New"),
            ("confirmed", "Confirmed"),
            ("progress", "Progress"),
            ("quality", "Quality check"),
            ("quality_confirmed", "Quality confirmed"),
            ("done", "Done"),
            ("cancelled", "Cancelled"),
        ],
    )

    @api.depends("appointment_id", "appointment_id.car_work_order_id.state")
    def _compute_order_state(self):
        for sale in self:
            order_state = "new"
            if sale.appointment_id and sale.appointment_id.car_work_order_id:
                order_state = sale.appointment_id.car_work_order_id.state
            sale.order_state = order_state
