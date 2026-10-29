from odoo import fields, models


class PortalHomeSlider(models.Model):
    _name = "portal.home.slider"
    _inherit = "image.mixin"
    _description = "Portal Home Slider"
    _order = "sequence, id"

    active = fields.Boolean(default=True)
    sequence = fields.Integer(default=10)
