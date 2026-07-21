from odoo import fields, models


class CarBom(models.Model):
    _name = "car.bom"
    _description = "Model year"

    service_id = fields.Many2one("product.product", string="Service")
    product_id = fields.Many2one(
        "product.product", string="Product", required=True, domain="[('detailed_type', '!=', 'service')]"
    )
    quantity = fields.Float(required=True)


class ProductProduct(models.Model):
    _inherit = "product.product"

    bom_ids = fields.One2many("car.bom", "service_id", "BOM")
    expected_duration = fields.Float()
    warranty = fields.Float()

    workshop_id = fields.Many2one("car.workshop", string="WorkShop")
    test = fields.Char(string="Test")
    is_test = fields.Boolean()
