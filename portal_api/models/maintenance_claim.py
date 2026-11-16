from odoo import fields, models


class WebsiteMaintenanceClaim(models.Model):
    _inherit = "maintenance.claim"

    website_request_user_id = fields.Many2one("res.users", string="Website Requester", readonly=True, copy=False)
