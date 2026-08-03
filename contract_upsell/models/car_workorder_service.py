from odoo import fields, models


class CarWorkorderService(models.Model):
    _inherit = "car.workorder.service"

    # Appointment and contract-upsell sync create services before staff is chosen.
    # Work order confirmation still enforces that at least one service has staff.
    staff_ids = fields.Many2many(
        "hr.employee",
        "car_workorder_service_staff_rel",
        "service_id",
        "employee_id",
        string="Staff",
        required=False,
    )
