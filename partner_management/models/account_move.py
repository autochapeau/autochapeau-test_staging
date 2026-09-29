from odoo import models, fields


class AccountMove(models.Model):
    _inherit = 'account.move'

    vehicle_id = fields.Many2one("fleet.vehicle", string="Car", readonly=True)
    vehicle_size = fields.Selection(related="vehicle_id.size", string="Car Size", readonly=True, )
    vehicle_color_id = fields.Many2one(related="vehicle_id.vehicle_color_id", string="Car Color", readonly=True)
    vehicle_vin_sn = fields.Char(related="vehicle_id.vin_sn", string="Chassis Number", readonly=True, )
    vehicle_model_year = fields.Char(related="vehicle_id.model_year", string="Model Year", readonly=True)
    plate_numbers = fields.Char(related="vehicle_id.plate_numbers")
    plate_letters = fields.Char(related="vehicle_id.plate_letters")

