from odoo import fields, models


class StockWarehouse(models.Model):
    _inherit = "stock.warehouse"

    branch_id = fields.Many2one(
        "hr.department",
        string="Branch",
        domain="[('department_type', '=', 'branche')]",
        help="Branch linked to warehouse.",
    )
