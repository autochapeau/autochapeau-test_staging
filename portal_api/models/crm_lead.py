from odoo import fields, models


class CrmLead(models.Model):
    _inherit = "crm.lead"

    model_id = fields.Many2one("fleet.vehicle.model", string="Car Model")
    model_year = fields.Integer(string="Model Year")
