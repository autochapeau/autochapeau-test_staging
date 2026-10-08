from odoo import api, models


class CarAppointment(models.Model):
    _inherit = "car.appointment"

    @api.model_create_multi
    def create(self, vals_list):
        appointments = super().create(vals_list)
        for appointment in appointments:
            claim = appointment.sale_order_id.maintenance_claim_id
            if claim and not claim.appointment_id:
                claim.sudo().appointment_id = appointment.id
        return appointments
