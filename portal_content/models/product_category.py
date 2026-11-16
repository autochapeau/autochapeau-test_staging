from odoo import fields, models


class ProductCategory(models.Model):
    _inherit = "product.category"

    portal_image = fields.Image(string="Website Category Icon", max_width=512, max_height=512)
