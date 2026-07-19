from random import randint

from odoo import fields, models


class PortalNews(models.Model):
    _name = "portal.news"
    _inherit = "image.mixin"
    _description = "Portal News"
    _order = "sequence,id"

    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)

    name = fields.Char(string="Title", required=True, translate=True)
    summary = fields.Text(translate=True)
    details = fields.Html(translate=True)
    tag_ids = fields.Many2many("portal.news.tag", string="Tags")
    date = fields.Date()


class PortalNewsTag(models.Model):
    _name = "portal.news.tag"
    _description = "Portal News Tag"
    _order = "name"

    def _get_default_color(self):
        return randint(1, 11)

    name = fields.Char("Tag Name", required=True, translate=True)
    color = fields.Integer("Color Index", default=_get_default_color)

    _sql_constraints = [
        ("name_uniq", "unique (name)", "Tag name already exists!"),
    ]
