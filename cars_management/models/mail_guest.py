from odoo import fields, models


class MailGuest(models.Model):
    _inherit = "mail.guest"

    name = fields.Char(translate=True)
