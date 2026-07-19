from odoo import api, fields, models


class ProductProduct(models.Model):
    _inherit = "product.product"

    old_sales_count = fields.Float(default=100)
    total_sales_count = fields.Float(default=100, readonly=True)

    @api.onchange("old_sales_count")
    def _onchange_old_sales_count(self):
        self.total_sales_count = self.sales_count + self.old_sales_count
