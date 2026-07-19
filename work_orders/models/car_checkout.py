from odoo import fields, models


class CarCheckout(models.Model):
    _inherit = "car.checkout"

    car_work_order_id = fields.Many2one("car.work.order")
