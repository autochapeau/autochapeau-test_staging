from odoo import fields, models


class PortalHomeLoyalty(models.Model):
    _name = "portal.home.loyalty"
    _description = "Portal Home Loyalty"
    _rec_name = "title"
    _order = "id desc"

    active = fields.Boolean(default=True)

    small_title = fields.Char(translate=True)
    title = fields.Char(required=True, translate=True)
    description = fields.Text(translate=True)
    subtitle = fields.Char(translate=True)
    button_label = fields.Char(translate=True)
    button_url = fields.Char()
    item_ids = fields.One2many("portal.home.loyalty.item", "loyalty_id")
    image_ids = fields.One2many("portal.home.loyalty.image", "loyalty_id")


class PortalHomeLoyaltyItem(models.Model):
    _name = "portal.home.loyalty.item"
    _description = "Portal Home Loyalty Item"
    _order = "sequence, id"
    _rec_name = "name"

    sequence = fields.Integer(default=10)
    loyalty_id = fields.Many2one(
        "portal.home.loyalty", required=True, ondelete="cascade"
    )
    name = fields.Char(required=True, translate=True)


class PortalHomeLoyaltyImage(models.Model):
    _name = "portal.home.loyalty.image"
    _inherit = "image.mixin"
    _description = "Portal Home Loyalty Image"
    _order = "sequence, id"
    _rec_name = "name"

    sequence = fields.Integer(default=10)
    loyalty_id = fields.Many2one(
        "portal.home.loyalty", required=True, ondelete="cascade"
    )
    name = fields.Char(translate=True)
