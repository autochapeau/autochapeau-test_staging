from odoo import _, api, fields, models
from odoo.exceptions import UserError


class WorkorderServiceQaCheckItem(models.Model):
    _name = "workorder.service.qa.check.item"
    _description = "Workorder Task QA Check Item"
    _order = "item_type, id"

    service_id = fields.Many2one(
        "car.workorder.service",
        string="Task",
        required=True,
        ondelete="cascade",
        index=True,
    )
    item_type = fields.Selection(
        [
            ("feature", "Feature"),
            ("bom", "BOM"),
        ],
        string="Type",
        required=True,
        default="feature",
        index=True,
    )
    feature_id = fields.Many2one(
        "product.feature",
        string="Feature",
        ondelete="set null",
    )
    bom_id = fields.Many2one(
        "car.bom",
        string="BOM Line",
        ondelete="set null",
    )
    product_id = fields.Many2one(
        "product.product",
        string="Product",
        ondelete="set null",
        help="BOM component product (copied at quality check time).",
    )
    quantity = fields.Float(string="Quantity", default=1.0)
    unit_cost = fields.Float(
        string="Unit Cost",
        digits="Product Price",
        help="Product cost snapshot at quality check time.",
    )
    cost = fields.Float(
        string="Cost",
        digits="Product Price",
        compute="_compute_cost",
        store=True,
    )
    name = fields.Char(
        string="Check Item",
        required=True,
        help="Copied from the product feature or BOM at quality check time.",
    )
    checked = fields.Boolean(string="Checked", default=False)

    @api.depends("quantity", "unit_cost")
    def _compute_cost(self):
        for line in self:
            line.cost = (line.quantity or 0.0) * (line.unit_cost or 0.0)

    def write(self, vals):
        if "checked" in vals and any(
            line.service_id.state != "quality" for line in self
        ):
            raise UserError(
                _("You can only update the quality list while the task is in Check Quality.")
            )
        return super().write(vals)
