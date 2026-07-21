from odoo import fields, models


class PartnerType(models.Model):
    _inherit = 'res.partner'

    partner_type = fields.Selection(
        [('customer', 'Customer'),
         ('supplier', 'Supplier'),
         ('employee', 'Employee')], default='customer')
