from odoo import fields, models


class PartnerType(models.Model):
    _inherit = 'res.partner'

    contact_type = fields.Selection(
        [('customer', 'Customer'),
         ('supplier', 'Supplier'),
         ('employee', 'Employee')], default='customer')


class AccountPayment(models.Model):
    _inherit = 'account.payment'

    contact_type = fields.Selection(related='partner_id.contact_type', store=True)