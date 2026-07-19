from odoo import api, fields, models


class CommissionSettlement(models.Model):
    _name = "commission.settlement"
    _description = "Settlement"
    _inherit = ["mail.thread", "mail.activity.mixin"]

    name = fields.Char(compute="_compute_name", store=True)
    commission_ids = fields.Many2many("commission", string="Commissions", required=True)
    total = fields.Float(compute="_compute_total", readonly=True, store=True)
    date_from = fields.Date(string="From", required=True)
    date_to = fields.Date(string="To", required=True)
    line_ids = fields.One2many(
        comodel_name="commission.settlement.line",
        inverse_name="settlement_id",
        string="Settlement lines",
        readonly=True,
    )
    state = fields.Selection(
        selection=[
            ("draft", "Draft"),
            ("settled", "Settled"),
            ("cancel", "Canceled"),
        ],
        readonly=True,
        required=True,
        default="draft",
    )
    currency_id = fields.Many2one(
        comodel_name="res.currency",
        readonly=True,
        default=lambda self: self._default_currency_id(),
        required=True,
    )
    company_id = fields.Many2one(
        comodel_name="res.company",
        default=lambda self: self._default_company_id(),
        required=True,
    )

    def _default_currency_id(self):
        return self.env.company.currency_id.id

    def _default_company_id(self):
        return self.env.company.id

    @api.depends("date_from", "date_to")
    def _compute_name(self):
        for settlement in self:
            settlement.name = f"{settlement.date_from}-{settlement.date_to}"

    @api.depends("line_ids", "line_ids.total_amount")
    def _compute_total(self):
        for record in self:
            record.total = sum(record.mapped("line_ids.total_amount"))

    def action_cancel(self):
        self.write({"state": "cancel"})

    def action_settle(self):
        self.ensure_one()
        self.generate_commission_lines()
        self.write({"state": "settled"})

    def generate_commission_lines(self):
        commissions = self.commission_ids
        commission_targets = {commission.id: {} for commission in commissions}
        for commission in commissions:
            for job_target in commission.job_target_ids:
                for job in job_target.job_id:
                    employees = self.env["hr.employee"].search([("job_id", "=", job.id)])
                    for employee in employees:
                        commission_targets[commission.id][employee.id] = job_target.target
            for employee_target in commission.employee_target_ids:
                commission_targets[commission.id][employee_target.employee_id.id] = employee_target.target
        lines = [(5, 0, 0)]
        commission_categories = self.env["commission.category"].search([])
        for commission_id in commission_targets:
            for employee_id in commission_targets[commission_id]:
                employee = self.env["hr.employee"].browse(employee_id)
                move_lines = self.env["account.move.line"].search(
                    [
                        ("move_id.invoice_user_id", "=", employee.user_id.id),
                        ("product_id.commission_category_id", "!=", False),
                        ("move_id.state", "=", "posted"),
                        ("invoice_date", ">=", self.date_from),
                        ("invoice_date", "<=", self.date_to),
                    ]
                )
                invoiced_amount = sum(line.price_subtotal for line in move_lines)
                current_target = commission_targets[commission_id][employee_id]
                percent = (invoiced_amount / current_target) * 100 if current_target else 0.0

                commission = self.env["commission"].browse(commission_id)
                discount_deduction = 0.0
                amount_to_settle = 0.0
                move_line_ids = []
                for categ in commission_categories:
                    for line in move_lines:
                        if line.product_id.commission_category_id.id == categ.id:
                            for section in commission.section_ids:
                                if section.amount_from <= percent <= section.amount_to:
                                    curr_amount = line.price_subtotal * (section.percent / 100)
                                    amount_to_settle += curr_amount
                                    move_line_ids.append(line.id)
                                    for discount_section in commission.discount_section_ids:
                                        if discount_section.amount_from <= line.discount <= discount_section.amount_to:
                                            discount_deduction += curr_amount * (
                                                discount_section.deduction_percent / 100
                                            )

                line = {
                    "commission_id": commission_id,
                    "employee_id": employee_id,
                    "target": commission_targets[commission_id][employee_id],
                    "invoiced_amount": invoiced_amount,
                    "percent": percent,
                    "amount_to_settle": amount_to_settle,
                    "discount_deduction": discount_deduction,
                    "total_amount": amount_to_settle - discount_deduction,
                    "move_line_ids": [(6, 0, move_line_ids)],
                }
                lines.append((0, 0, line))
        self.line_ids = lines


class SettlementLine(models.Model):
    _name = "commission.settlement.line"
    _description = "Line of a commission settlement"

    settlement_id = fields.Many2one(
        "commission.settlement",
        readonly=True,
        ondelete="cascade",
        required=True,
    )
    employee_id = fields.Many2one("hr.employee", readonly=True)

    target = fields.Float(readonly=True)
    invoiced_amount = fields.Float(readonly=True)
    percent = fields.Float(readonly=True)
    amount_to_settle = fields.Float(readonly=True)
    discount_deduction = fields.Float(readonly=True)
    total_amount = fields.Monetary(readonly=True)
    move_line_ids = fields.Many2many("account.move.line", string="Invoices lines", readonly=True)
    currency_id = fields.Many2one(
        related="settlement_id.currency_id",
        comodel_name="res.currency",
        store=True,
        readonly=True,
    )
    commission_id = fields.Many2one(
        comodel_name="commission",
        readonly=True,
        required=True,
    )
    company_id = fields.Many2one(
        comodel_name="res.company",
        related="settlement_id.company_id",
        store=True,
    )
