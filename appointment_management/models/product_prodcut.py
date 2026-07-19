from odoo import fields, models


class ProductProduct(models.Model):
    _inherit = "product.product"

    lst_price_discount = fields.Float(string="Price after discount")
