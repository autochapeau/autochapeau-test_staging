from odoo import fields, models


class ProductProduct(models.Model):
    _inherit = "product.product"

    is_published = fields.Boolean(string="Is Published", default=False)
