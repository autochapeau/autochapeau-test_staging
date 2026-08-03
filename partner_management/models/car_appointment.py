from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class CarAppointment(models.Model):
    _inherit = "car.appointment"

    def action_view_work_order(self):
        """Open the work order generated from this appointment."""
        self.ensure_one()
        if not self.car_work_order_id:
            raise ValidationError(_(
                "No work order is linked to this appointment."
            ))
        return {
            "type": "ir.actions.act_window",
            "name": _("Work Order"),
            "res_model": "car.work.order",
            "res_id": self.car_work_order_id.id,
            "view_mode": "form",
            "views": [(
                self.env.ref("work_orders.car_work_order_view_form").id,
                "form",
            )],
            "target": "current",
        }

    def action_view_checkin(self):
        """Open the check-in linked to this appointment."""
        self.ensure_one()
        if not self.car_checkin_id:
            raise ValidationError(_(
                "No check-in is linked to this appointment."
            ))
        return {
            "type": "ir.actions.act_window",
            "name": _("Check-In"),
            "res_model": "car.checkin",
            "res_id": self.car_checkin_id.id,
            "view_mode": "form",
            "views": [(
                self.env.ref("cars_management.car_checkin_view_form").id,
                "form",
            )],
            "target": "current",
        }

    @api.constrains("sale_order_id")
    def _check_one_appointment_per_sale_order(self):
        for appointment in self.filtered("sale_order_id"):
            duplicate_count = self.search_count([
                ("sale_order_id", "=", appointment.sale_order_id.id),
                ("id", "!=", appointment.id),
            ])
            if duplicate_count:
                raise ValidationError(_(
                    "Only one appointment can be linked to each sale order."
                ))

    @api.constrains("appointment_slot_id", "maintenance_slot_id")
    def _check_appointment_slots_not_in_past(self):
        for appointment in self:
            today = fields.Date.context_today(appointment)
            slots = (
                appointment.appointment_slot_id
                | appointment.maintenance_slot_id
            )
            if any(slot.date and slot.date < today for slot in slots):
                raise ValidationError(_(
                    "Appointment and maintenance slots cannot be before "
                    "today's date."
                ))
