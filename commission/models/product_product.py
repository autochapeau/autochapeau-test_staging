from odoo import fields, models


class ProductProduct(models.Model):
    _inherit = "product.product"

    commission_category_id = fields.Many2one("commission.category")
    technicians_commission_amount = fields.Float()
