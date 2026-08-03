from odoo import fields, models


class ProductTemplate(models.Model):
    _inherit = "product.template"

    is_window_tinting = fields.Boolean(
        string="Window Tinting Service",
        help="Enable this option when sales order lines must include glass type and tint percentage.",
    )

    allowed_glass_type_ids = fields.Many2many(
        comodel_name="window.tint.glass.type",
        relation="product_template_window_tint_glass_type_rel",
        column1="product_tmpl_id",
        column2="glass_type_id",
        string="Allowed Glass Types",
        help="Leave empty to allow all active glass types.",
    )

    allowed_tint_percentage_ids = fields.Many2many(
        comodel_name="window.tint.percentage",
        relation="product_template_window_tint_percentage_rel",
        column1="product_tmpl_id",
        column2="tint_percentage_id",
        string="Allowed Tint Percentages",
        help="Leave empty to allow all active tint percentages.",
    )
