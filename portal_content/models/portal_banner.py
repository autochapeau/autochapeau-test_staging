from odoo import fields, models


class PortalBanner(models.Model):
    _name = "portal.banner"
    _inherit = "image.mixin"
    _description = "Portal Banner"
    _rec_name = "first_title"

    active = fields.Boolean(default=True)

    # Keep the legacy selection field so Odoo can complete the migration from
    # version 17.0.1.0.6, where it was introduced as a Selection field.
    # New banners use page_name, which deliberately accepts any portal page.
    page = fields.Selection(
        selection=[
            ("offers", "Offers"),
            ("aboutus", "About Us"),
            ("jobs", "Jobs"),
        ],
    )
    page_name = fields.Char()
    first_title = fields.Char(required=True, translate=True)
    second_title = fields.Char(translate=True)
    url = fields.Char()
