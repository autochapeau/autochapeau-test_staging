from odoo import fields, models


class PortalOffer(models.Model):
    _name = "portal.offer"
    _inherit = "image.mixin"
    _description = "Portal Offer"

    active = fields.Boolean(default=True)

    name = fields.Char(string="Title", required=True, translate=True)
    summary = fields.Text(translate=True)
    details = fields.Html(translate=True)
