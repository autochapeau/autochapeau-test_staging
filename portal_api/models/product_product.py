from odoo import fields, models


class ProductProduct(models.Model):
    _inherit = "product.product"

    web_note = fields.Text(string="Web Note", translate=True)
