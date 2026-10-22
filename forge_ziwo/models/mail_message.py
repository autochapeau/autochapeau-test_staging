from odoo import models, fields, api

class MailMessage(models.Model):
    _inherit = 'mail.message'

    body = fields.Html(sanitize_attributes=False)