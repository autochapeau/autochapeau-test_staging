from odoo import fields, models


class CarCheckin(models.Model):
    _inherit = "car.checkin"

    appointment_id = fields.Many2one("car.appointment")
