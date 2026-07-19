from odoo import fields, models


class MessageModel(models.Model):
    _name = "message.model"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _description = "Message Model"

    name = fields.Char(required=True, tracking=True)
    message = fields.Text(required=True, tracking=True, translate=True)
    model_ids = fields.Many2many(
        "ir.model",
        help="In which models this message model will appear.",
    )
