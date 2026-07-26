from odoo import api, fields, models


class PosOrder(models.Model):
    _inherit = "pos.order"

    appointment_id = fields.Many2one(
        "car.appointment",
        string="Appointment",
        copy=False,
        index=True,
    )

    @api.model
    def _order_fields(self, ui_order):
        fields = super()._order_fields(ui_order)
        fields["appointment_id"] = ui_order.get("appointment_id") or False
        return fields

    def _export_for_ui(self, order):
        result = super()._export_for_ui(order)
        result["appointment_id"] = order.appointment_id.id if order.appointment_id else False
        result["appointment_name"] = order.appointment_id.name if order.appointment_id else False
        return result

    @api.model
    def _process_order(self, order, draft, existing_order):
        order_id = super()._process_order(order, draft, existing_order)
        pos_order = self.browse(order_id)
        pos_order._link_appointment_from_pos_uid()
        return order_id

    def _link_appointment_from_pos_uid(self):
        """Link appointment created from POS before the order was synced."""
        for order in self:
            if order.appointment_id:
                if not order.appointment_id.pos_order_id:
                    order.appointment_id.sudo().write({"pos_order_id": order.id})
                continue
            if not order.pos_reference:
                continue
            appointment = self.env["car.appointment"].sudo().search(
                [
                    ("pos_uid", "=", order.pos_reference),
                    "|",
                    ("pos_order_id", "=", False),
                    ("pos_order_id", "=", order.id),
                ],
                limit=1,
                order="id desc",
            )
            if appointment:
                appointment.write({"pos_order_id": order.id})
                order.write({"appointment_id": appointment.id})

    def action_view_appointment(self):
        self.ensure_one()
        if not self.appointment_id:
            return False
        action = self.env["ir.actions.actions"]._for_xml_id(
            "appointment_management.car_appointment_action"
        )
        action["views"] = [(False, "form")]
        action["res_id"] = self.appointment_id.id
        return action

    def action_book_appointment(self):
        """Open a new appointment prefilled from this POS order (backend)."""
        self.ensure_one()
        if self.appointment_id:
            return self.action_view_appointment()
        return {
            "type": "ir.actions.act_window",
            "name": "Book Appointment",
            "res_model": "car.appointment",
            "view_mode": "form",
            "target": "current",
            "context": {
                "default_partner_id": self.partner_id.id if self.partner_id else False,
                "default_vehicle_id": self.vehicle_id.id if self.vehicle_id else False,
                "default_pos_order_id": self.id,
                "default_pos_uid": self.pos_reference or False,
            },
        }
