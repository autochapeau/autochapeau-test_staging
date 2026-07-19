from odoo import fields, models, _


class ProductCategory(models.Model):
    _inherit = "product.category"

    category_type = fields.Selection(
        [("service", _("Service")), ("other", _("Other"))])
    name = fields.Char(translate=True)


class ProductTemplate(models.Model):
    _inherit = "product.template"

    company_ids = fields.Many2many("res.company", string="Branches")
    is_large = fields.Boolean()
    is_medium = fields.Boolean()
    is_small = fields.Boolean()
    description_website = fields.Html(
        string="Website Description", translate=True)
    feature_ids = fields.Many2many(
        "product.feature", string="Features")
    features_description = fields.Html(translate=True)

    def _get_published_variants_for_vehicle(self, vehicle):
        """Return the published variants of this service relevant for the vehicle"""
        self.ensure_one()
        published = self.product_variant_ids.filtered("is_published")
        has_size = any(line.attribute_id.with_context(lang="en_US").name.strip(
        ).lower() == "size" for line in self.attribute_line_ids)
        if not has_size or not vehicle.size:
            return published
        return published.filtered(
            lambda v: vehicle.size in v.product_template_variant_value_ids.product_attribute_value_id.mapped("code")
        )


class ProductFeature(models.Model):
    _name = "product.feature"
    _description = "Products Features"

    name = fields.Char(required=True, translate=True)
