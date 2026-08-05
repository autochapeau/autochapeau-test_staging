from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError


class ExternalReferral(models.Model):
    _name = "external.referral"
    _description = "External Referral"
    _order = "invoice_date desc, id desc"

    name = fields.Char(required=True, readonly=True, copy=False)
    commission_type = fields.Selection(
        [
            ("autochapeau", "Autochapeau"),
            ("autoflex", "Autoflex"),
        ],
        string="Commission Type",
        required=True,
        readonly=True,
        index=True,
    )
    agency_id = fields.Many2one(
        "res.partner",
        string="Agency",
        required=True,
        readonly=True,
        ondelete="restrict",
    )
    agency_salesperson_id = fields.Many2one(
        "res.partner",
        string="Agency Salesperson",
        required=True,
        readonly=True,
        ondelete="restrict",
    )
    sale_order_id = fields.Many2one(
        "sale.order",
        required=True,
        readonly=True,
        ondelete="restrict",
    )
    invoice_id = fields.Many2one(
        "account.move",
        required=True,
        readonly=True,
        ondelete="restrict",
        domain="[('move_type', '=', 'out_invoice')]",
    )
    invoice_date = fields.Date(
        related="invoice_id.invoice_date",
        store=True,
        readonly=True,
    )
    company_id = fields.Many2one(
        "res.company",
        required=True,
        readonly=True,
    )
    currency_id = fields.Many2one(
        "res.currency",
        required=True,
        readonly=True,
    )
    base_amount = fields.Monetary(
        string="Untaxed Base",
        currency_field="currency_id",
        required=True,
        readonly=True,
        help="Workshop untaxed product total used to compute the percentage.",
    )
    referral_percent = fields.Float(
        string="Referral (%)",
        digits=(16, 2),
        required=True,
        help="Editable by Accounting / Sales Managers after the invoice is paid.",
    )
    amount = fields.Monetary(
        string="Referral Amount",
        currency_field="currency_id",
        required=True,
        help="Amount due to the agency salesperson for this commission type.",
    )
    state = fields.Selection(
        [
            ("due", "Due"),
            ("paid", "Paid"),
            ("cancelled", "Cancelled"),
        ],
        required=True,
        default="due",
        readonly=True,
    )
    paid_date = fields.Date(readonly=True, copy=False)
    payment_reference = fields.Char(copy=False)
    note = fields.Text()

    _sql_constraints = [
        (
            "invoice_sale_order_type_unique",
            "unique(invoice_id, sale_order_id, commission_type)",
            "An external referral already exists for this invoice, sale order and commission type.",
        ),
    ]

    def _user_can_edit_amounts(self):
        return (
            self.env.su
            or self.env.user.has_group("account.group_account_manager")
            or self.env.user.has_group("sales_team.group_sale_manager")
        )

    def write(self, vals):
        amount_keys = {"amount", "referral_percent", "base_amount"}
        if amount_keys & set(vals) and not self._user_can_edit_amounts():
            raise AccessError(_(
                "Only Accounting Managers or Sales Managers can change "
                "referral amounts or percentages."
            ))
        if self.filtered(lambda r: r.state == "cancelled") and amount_keys & set(vals):
            raise UserError(_("Cancelled referrals cannot be modified."))

        # Keep amount and % in sync when managers edit after invoice payment.
        if "referral_percent" in vals and "amount" not in vals:
            for referral in self:
                base = vals.get("base_amount", referral.base_amount) or 0.0
                percent = vals["referral_percent"] or 0.0
                amount = (
                    referral.currency_id.round(base * percent / 100.0) if base else 0.0
                )
                super(ExternalReferral, referral).write({**vals, "amount": amount})
            return True
        if "amount" in vals and "referral_percent" not in vals:
            for referral in self:
                base = vals.get("base_amount", referral.base_amount) or 0.0
                amount = vals["amount"] or 0.0
                percent = (amount / base * 100.0) if base else 0.0
                super(ExternalReferral, referral).write({
                    **vals,
                    "referral_percent": percent,
                })
            return True
        return super().write(vals)

    @api.onchange("referral_percent", "base_amount")
    def _onchange_referral_percent(self):
        for referral in self:
            if referral.base_amount:
                referral.amount = referral.currency_id.round(
                    referral.base_amount * referral.referral_percent / 100.0
                )

    @api.onchange("amount", "base_amount")
    def _onchange_amount(self):
        for referral in self:
            if referral.base_amount:
                referral.referral_percent = (
                    referral.amount / referral.base_amount * 100.0
                )
            elif not referral.amount:
                referral.referral_percent = 0.0

    def _order_has_manual_commissions(self, order):
        return bool(
            order.commission_autochapeau_amount or order.commission_autoflex_amount
        )

    def _commission_lines_from_order(self, order, currency):
        """Build Autochapeau / Autoflex referral payloads from SO manual amounts."""
        lines = []
        if order.commission_autochapeau_amount:
            base = order.commission_autochapeau_base or 0.0
            amount = currency.round(order.commission_autochapeau_amount)
            percent = (
                order.commission_autochapeau_percent
                if base
                else 0.0
            )
            lines.append({
                "commission_type": "autochapeau",
                "base_amount": base,
                "referral_percent": percent,
                "amount": amount,
            })
        if order.commission_autoflex_amount:
            base = order.commission_autoflex_base or 0.0
            amount = currency.round(order.commission_autoflex_amount)
            percent = (
                order.commission_autoflex_percent
                if base
                else 0.0
            )
            lines.append({
                "commission_type": "autoflex",
                "base_amount": base,
                "referral_percent": percent,
                "amount": amount,
            })
        return lines

    def _prepare_referral_values(self, invoice, order, line_vals):
        type_label = dict(self._fields["commission_type"].selection).get(
            line_vals["commission_type"], line_vals["commission_type"]
        )
        return {
            "name": _(
                "%(invoice)s - %(type)s - %(salesperson)s",
                invoice=invoice.name,
                type=type_label,
                salesperson=order.agency_salesperson_id.display_name,
            ),
            "commission_type": line_vals["commission_type"],
            "agency_id": order.agency_id.id,
            "agency_salesperson_id": order.agency_salesperson_id.id,
            "sale_order_id": order.id,
            "invoice_id": invoice.id,
            "company_id": invoice.company_id.id,
            "currency_id": invoice.currency_id.id,
            "base_amount": line_vals["base_amount"],
            "referral_percent": line_vals["referral_percent"],
            "amount": line_vals["amount"],
            "state": "due",
            "paid_date": False,
        }

    def _eligible_orders_for_invoice(self, invoice):
        return invoice.invoice_line_ids.sale_line_ids.order_id.filtered(
            lambda order: (
                order.order_type == "extern"
                and order.agency_id
                and order.agency_salesperson_id
                and self._order_has_manual_commissions(order)
            )
        )

    @api.model
    def _sync_paid_invoices(self, invoices):
        """Create one due referral per commission type when the invoice is paid."""
        for invoice in invoices.filtered(
            lambda move: (
                move.move_type == "out_invoice"
                and move.state == "posted"
                and move.payment_state in ("paid", "in_payment")
            )
        ):
            orders = self._eligible_orders_for_invoice(invoice)
            for order in orders:
                for line_vals in self._commission_lines_from_order(
                    order, invoice.currency_id
                ):
                    if invoice.currency_id.is_zero(line_vals["amount"]):
                        continue
                    values = self._prepare_referral_values(invoice, order, line_vals)
                    referral = self.search([
                        ("invoice_id", "=", invoice.id),
                        ("sale_order_id", "=", order.id),
                        ("commission_type", "=", line_vals["commission_type"]),
                    ], limit=1)
                    if not referral:
                        self.create(values)
                    elif referral.state != "paid":
                        referral.write(values)

    @api.model
    def _cancel_open_for_invoices(self, invoices):
        referrals = self.search([
            ("invoice_id", "in", invoices.ids),
            ("state", "=", "due"),
        ])
        referrals.write({"state": "cancelled"})

    def action_generate_referrals(self):
        invoices = self.env["account.move"].search([
            ("move_type", "=", "out_invoice"),
            ("state", "=", "posted"),
            ("payment_state", "in", ("paid", "in_payment")),
            ("invoice_line_ids.sale_line_ids.order_id.order_type", "=", "extern"),
        ])
        before_count = self.search_count([])
        self._sync_paid_invoices(invoices)
        created_count = self.search_count([]) - before_count
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("External Referrals"),
                "message": _(
                    "%(created)s referral(s) generated from "
                    "%(invoices)s eligible paid invoice(s).",
                    created=created_count,
                    invoices=len(invoices),
                ),
                "type": "success",
                "sticky": False,
                "next": {
                    "type": "ir.actions.client",
                    "tag": "soft_reload",
                },
            },
        }

    def action_mark_paid(self):
        for referral in self:
            if referral.state != "due":
                raise UserError(_(
                    "Only due referrals can be marked as paid."
                ))
        self.write({
            "state": "paid",
            "paid_date": fields.Date.context_today(self),
        })
        return True

    def action_reset_to_due(self):
        self.write({
            "state": "due",
            "paid_date": False,
        })
        return True
