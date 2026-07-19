from uuid import uuid4

from odoo import api, fields, models
from odoo.tools import float_round


class SaleOrder(models.Model):
    _inherit = "sale.order"

    agency_id = fields.Many2one(
        "res.partner", string="Agency Name", domain="[('category_id.name', '=', 'Agency')]")
    agency_salesperson_id = fields.Many2one(
        "res.partner", string="Agency Salesperson", domain="[('parent_id', '=', agency_id)]")
    commission_amount = fields.Float(string="Commission Amount")

    branch_id = fields.Many2one(
        'hr.department',
        string='Branche',
        domain="[('department_type', '=', 'branche')]",
        help="Branch related to the order."
    )

    order_type = fields.Selection([
        ('intern', 'Intern'),
        ('extern', 'Extern'),
        ('contract', 'Contract'),
    ], string="Order Type", default='intern', required=True)

    donation_amount = fields.Float(compute="_compute_donation_amount")
    access_token = fields.Char(default=lambda self: str(uuid4()), copy=False)

    @api.onchange('agency_id')
    def _onchange_agency_id_reset_salesperson(self):
        """Reset the agency salesperson when the agency changes."""
        self.agency_salesperson_id = False

    @api.onchange('appointment_id')
    def _onchange_appointment_id_set_branch_and_analytic(self):
        """
        When an appointment is linked, automatically fill in the branch and analytic account
        according to the branch of the appointment.
        """
        if self.appointment_id and self.appointment_id.branch_id:
            self.branch_id = self.appointment_id.branch_id.id
            # If the branch has an analytic account, fill it in as well
            if self.appointment_id.branch_id.analytic_account_id:
                self.analytic_account_id = self.appointment_id.branch_id.analytic_account_id.id

    def _branch_warehouse(self):
        """Return the warehouse linked to the order's branch (stock follows the branch)."""
        self.ensure_one()
        if not self.branch_id:
            return self.env["stock.warehouse"]
        return self.env["stock.warehouse"].sudo().search(
            [("branch_id", "=", self.branch_id.id),
             ("company_id", "=", self.company_id.id)], limit=1)

    @api.onchange('branch_id')
    def _onchange_branch_id_set_analytic(self):
        """
        When a branch is selected, fill in its analytic account and use the
        warehouse of that branch (so the stock operations stay in the branch).
        """
        if self.branch_id and self.branch_id.analytic_account_id:
            self.analytic_account_id = self.branch_id.analytic_account_id.id
        warehouse = self._branch_warehouse()
        if warehouse:
            self.warehouse_id = warehouse.id

    @api.depends("transaction_ids", "transaction_ids.donation_amount")
    def _compute_donation_amount(self):
        for order in self:
            order.donation_amount = sum(
                order.transaction_ids.mapped("donation_amount"))

    def _align_warehouse_with_branch(self):
        """Force the warehouse to the branch warehouse for orders not delivered yet."""
        for order in self:
            if order.state in ("draft", "sent") and order.branch_id:
                warehouse = order._branch_warehouse()
                if warehouse and order.warehouse_id != warehouse:
                    order.warehouse_id = warehouse

    @api.model_create_multi
    def create(self, vals_list):
        orders = super().create(vals_list)
        orders._align_warehouse_with_branch()
        return orders

    def write(self, vals):
        res = super().write(vals)
        if "branch_id" in vals:
            self._align_warehouse_with_branch()
        return res

    def action_confirm(self):
        result = super().action_confirm()
        for order in self:
            for line in order.order_line:
                product = line.product_id
                product.total_sales_count = float_round(
                    product.sales_count + product.old_sales_count + line.product_uom_qty,
                    precision_rounding=product.uom_id.rounding,
                )

        return result
