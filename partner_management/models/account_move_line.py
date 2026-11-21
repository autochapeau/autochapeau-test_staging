from odoo import fields, models


class AccountMoveLine(models.Model):
    _inherit = "account.move.line"

    invoice_user_id = fields.Many2one(related="move_id.invoice_user_id", store=True)
    product_category_id = fields.Many2one(
        string="Product Category",
        related="product_id.categ_id",
        store=True,
    )
