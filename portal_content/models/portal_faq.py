from odoo import fields, models


class PortalFaq(models.Model):
    _name = "portal.faq"
    _description = "Portal FAQ"
    _rec_name = "question"
    _order = "sequence,id"

    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)

    question = fields.Char(required=True, translate=True)
    answer = fields.Html(required=True, translate=True)
