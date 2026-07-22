from odoo import models, fields, api


class PartnerInheritType(models.Model):
    _inherit = 'res.partner'

    contact_partner_type = fields.Selection(
        [('customer', 'Customer'),
         ('supplier', 'Supplier'),
         ('employee', 'Employee')], default='customer', string='Contact **')
