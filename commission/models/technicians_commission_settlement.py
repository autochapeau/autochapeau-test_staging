from odoo import api, fields, models


class TechniciansCommissionSettlement(models.Model):
    _name = "technicians.commission.settlement"
    _description = "Technicians Commissions Settlement"
    _inherit = ["mail.thread", "mail.activity.mixin"]

    name = fields.Char(compute="_compute_name", store=True)
    total = fields.Float(compute="_compute_total", readonly=True, store=True)
    date_from = fields.Date(string="From", required=True)
    date_to = fields.Date(string="To", required=True)
    line_ids = fields.One2many(
        comodel_name="technicians.commission.settlement.line",
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

    @api.depends("line_ids", "line_ids.amount")
    def _compute_total(self):
        for record in self:
            record.total = sum(record.mapped("line_ids.amount"))

    def action_cancel(self):
        self.write({"state": "cancel"})

    def action_settle(self):
        self.ensure_one()
        self.generate_commission_lines()
        self.write({"state": "settled"})

    def generate_commission_lines(self):
        services = self.env["car.workorder.service"].search(
            [("date_end", ">=", self.date_from), ("date_end", "<=", self.date_to), ("workorder_id.state", "=", "done")]
        )
        amounts_by_emp = {}
        for service in services:
            commission_amount = service.product_id.technicians_commission_amount
            employees = service.workcenter_id.employee_ids
            employees_count = len(employees)
            for employee in employees:
                if amounts_by_emp.get(employee.id):
                    amounts_by_emp[employee.id]["amount"] += commission_amount / employees_count
                    amounts_by_emp[employee.id]["service_ids"].append(service.product_id.id)
                else:
                    amounts_by_emp[employee.id] = {
                        "amount": commission_amount / employees_count,
                        "service_ids": [service.product_id.id],
                    }
        lines = [(5, 0, 0)]
        for employee_id in amounts_by_emp:
            line = {
                "employee_id": employee_id,
                "service_ids": [(6, 0, amounts_by_emp[employee.id]["service_ids"])],
                "amount": amounts_by_emp[employee.id]["amount"],
            }
            lines.append((0, 0, line))
        self.line_ids = lines


class TechniciansSettlementLine(models.Model):
    _name = "technicians.commission.settlement.line"
    _description = "Line of a technician commission settlement"

    settlement_id = fields.Many2one(
        "technicians.commission.settlement",
        readonly=True,
        ondelete="cascade",
        required=True,
    )

    employee_id = fields.Many2one("hr.employee", readonly=True)
    service_ids = fields.Many2many("product.product", string="Services", readonly=True)
    amount = fields.Monetary(readonly=True)
    currency_id = fields.Many2one(
        related="settlement_id.currency_id",
        comodel_name="res.currency",
        store=True,
        readonly=True,
    )
    company_id = fields.Many2one(
        comodel_name="res.company",
        related="settlement_id.company_id",
        store=True,
    )
