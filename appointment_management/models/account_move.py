from uuid import uuid4

from odoo import fields, models


class AccountMove(models.Model):
    _inherit = "account.move"

    access_token = fields.Char(default=lambda self: str(uuid4()), copy=False)
    vehicle_id = fields.Many2one("fleet.vehicle", readonly=True)
    # todo: get vehicle from SO  ?
