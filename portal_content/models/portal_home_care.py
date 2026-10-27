from odoo import fields, models


class PortalHomeCare(models.Model):
    _name = "portal.home.care"
    _description = "Portal Home Care"
    _rec_name = "title"
    _order = "id desc"

    active = fields.Boolean(default=True)

    title = fields.Char(required=True, translate=True)
    description = fields.Text(translate=True)
    item_ids = fields.One2many("portal.home.care.item", "care_id")


class PortalHomeCareItem(models.Model):
    _name = "portal.home.care.item"
    _inherit = "image.mixin"
    _description = "Portal Home Care Item"
    _order = "sequence, id"
    _rec_name = "title"

    sequence = fields.Integer(default=10)
    care_id = fields.Many2one("portal.home.care", required=True, ondelete="cascade")
    title = fields.Char(required=True, translate=True)
    description = fields.Char(translate=True)
