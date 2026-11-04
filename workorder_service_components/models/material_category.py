from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class ProductCategory(models.Model):
    _inherit = "product.category"

    is_main_material_category = fields.Boolean(
        string="Main Material Category",
        help="Allow this category and its subcategories when configuring service materials.",
    )


class CarBom(models.Model):
    _inherit = "car.bom"

    material_category_id = fields.Many2one(
        "product.category", string="Material Category", ondelete="restrict",
        domain="[('is_main_material_category', '=', True)]",
    )

    @api.onchange("material_category_id")
    def _onchange_material_category_id(self):
        if self.product_id and self.material_category_id and not self.env["product.product"].search_count([
            ("id", "=", self.product_id.id),
            ("categ_id", "child_of", self.material_category_id.id),
        ]):
            self.product_id = False

    @api.constrains("material_category_id")
    def _check_main_material_category(self):
        if any(line.material_category_id and not line.material_category_id.is_main_material_category for line in self):
            raise ValidationError(_("Select a main material category."))

    @api.constrains("material_category_id", "product_id")
    def _check_material_category(self):
        for line in self.filtered("material_category_id"):
            if not self.env["product.product"].search_count([
                ("id", "=", line.product_id.id),
                ("categ_id", "child_of", line.material_category_id.id),
                ("detailed_type", "=", "product"),
            ]):
                raise ValidationError(_("Select a storable material from the selected category or its subcategories."))
