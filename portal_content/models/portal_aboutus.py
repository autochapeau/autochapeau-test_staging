from odoo import fields, models


class PortalAboutus(models.Model):
    _name = "portal.aboutus"
    _inherit = "image.mixin"
    _description = "Portal About us"

    active = fields.Boolean(default=True)

    name = fields.Char(string="Title", required=True, translate=True)
    summary = fields.Text(translate=True)
    details = fields.Html(translate=True)
    secondary_image = fields.Image(
        string="Small Image", max_width=1920, max_height=1920,
        help="Independent image for the smaller frame on the About Us page.",
    )
