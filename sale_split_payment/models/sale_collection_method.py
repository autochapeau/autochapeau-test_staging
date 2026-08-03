from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class SaleCollectionMethod(models.Model):
    _name = "sale.collection.method"
    _description = "Sale Order Collection Method"
    _order = "sequence, id"
    _check_company_auto = True

    name = fields.Char(required=True, translate=True)
    code = fields.Char(required=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    company_id = fields.Many2one(
        "res.company",
        required=True,
        default=lambda self: self.env.company,
        index=True,
    )
    processing_type = fields.Selection(
        [
            ("manual", "Manual"),
            ("terminal", "Card Terminal"),
            ("tabby", "Tabby"),
        ],
        required=True,
        default="manual",
        help=(
            "Manual: create and post an account payment immediately "
            "(cash, bank transfer, cheque, ...).\n"
            "Card Terminal: send the amount to the configured terminal API.\n"
            "Tabby: open Tabby checkout and post the payment only after approval."
        ),
    )
    journal_id = fields.Many2one(
        "account.journal",
        string="Payment Journal",
        domain="[('type', 'in', ('cash', 'bank')), ('company_id', '=', company_id)]",
        check_company=True,
        help="Inbound payments for this method are posted to this journal.",
    )
    payment_method_line_id = fields.Many2one(
        "account.payment.method.line",
        string="Payment Method Line",
        domain="[('id', 'in', available_payment_method_line_ids)]",
        check_company=True,
    )
    available_payment_method_line_ids = fields.Many2many(
        "account.payment.method.line",
        compute="_compute_available_payment_method_line_ids",
    )
    require_reference = fields.Boolean(
        string="Require Reference",
        help="Ask the cashier for a bank/transfer reference before collecting.",
    )
    notes = fields.Text()

    _sql_constraints = [
        (
            "code_company_uniq",
            "unique(code, company_id)",
            "The collection method code must be unique per company.",
        ),
    ]

    @api.depends("journal_id")
    def _compute_available_payment_method_line_ids(self):
        for method in self:
            method.available_payment_method_line_ids = (
                method.journal_id.inbound_payment_method_line_ids
            )

    @api.onchange("journal_id")
    def _onchange_journal_id(self):
        for method in self:
            if (
                method.payment_method_line_id
                and method.payment_method_line_id not in method.available_payment_method_line_ids
            ):
                method.payment_method_line_id = False
            if not method.payment_method_line_id and method.available_payment_method_line_ids:
                method.payment_method_line_id = method.available_payment_method_line_ids[:1]

    @api.constrains("journal_id", "payment_method_line_id")
    def _check_payment_method_line(self):
        for method in self:
            if (
                method.payment_method_line_id
                and method.journal_id
                and method.payment_method_line_id.journal_id != method.journal_id
            ):
                raise ValidationError(
                    _("The payment method line must belong to the selected journal.")
                )

    def resolve_journal(self):
        """Journal to post to: the configured one, or a sensible company default."""
        self.ensure_one()
        if self.journal_id:
            return self.journal_id
        preferred_type = "cash" if self.processing_type == "manual" else "bank"
        Journal = self.env["account.journal"]
        domain = [("company_id", "=", self.company_id.id)]
        journal = Journal.search(domain + [("type", "=", preferred_type)], limit=1)
        if not journal:
            journal = Journal.search(
                domain + [("type", "in", ("cash", "bank"))], limit=1
            )
        return journal

    def get_payment_method_line(self, journal=None):
        """Return the inbound payment method line to use for ``journal``.

        ``journal`` defaults to the journal configured on this method, but the
        cashier may override it on the payment itself.
        """
        self.ensure_one()
        journal = journal or self.journal_id
        if not journal:
            return self.env["account.payment.method.line"]
        if (
            self.payment_method_line_id
            and self.payment_method_line_id.journal_id == journal
        ):
            return self.payment_method_line_id
        return journal.inbound_payment_method_line_ids[:1]
