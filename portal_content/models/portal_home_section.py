from odoo import fields, models


class PortalHomeSection(models.Model):
    _name = "portal.home.section"
    _inherit = "image.mixin"
    _description = "Portal Home Section"
    _rec_name = "title"
    _order = "id desc"

    active = fields.Boolean(default=True)

    small_title = fields.Char(translate=True)
    title = fields.Char(required=True, translate=True)
    description = fields.Text(translate=True)
    video_url = fields.Char()
    item_ids = fields.One2many("portal.home.section.item", "section_id")


class PortalHomeSectionItem(models.Model):
    _name = "portal.home.section.item"
    _description = "Portal Home Section Item"
    _order = "sequence, id"

    sequence = fields.Integer(default=10)
    section_id = fields.Many2one(
        "portal.home.section", required=True, ondelete="cascade"
    )
    name = fields.Char(required=True, translate=True)
