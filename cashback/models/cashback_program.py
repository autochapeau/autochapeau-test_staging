# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class CashbackProgram(models.Model):
    _name = "cashback.program"
    _description = "Cashback Program"
    _order = "date_start desc, id desc"

    name = fields.Char(required=True, translate=True)
    active = fields.Boolean(default=True)
    company_id = fields.Many2one(
        "res.company",
        required=True,
        default=lambda self: self.env.company,
    )
    currency_id = fields.Many2one(
        related="company_id.currency_id",
        store=True,
    )
    date_start = fields.Date(required=True, string="Start Date")
    date_end = fields.Date(required=True, string="End Date")
    percentage = fields.Float(
        string="Cashback %",
        required=True,
        default=48.0,
        help="Percentage of the invoice base amount credited to the wallet. "
             "Example: 48 means 4.8 SAR cashback for every 10 SAR.",
    )
    amount_basis = fields.Selection(
        [
            ("untaxed", "Untaxed Amount"),
            ("total", "Total Amount (incl. tax)"),
        ],
        string="Amount Basis",
        required=True,
        default="untaxed",
        help="Invoice amount used to compute cashback.",
    )
    notify_sms = fields.Boolean(
        string="Notify by SMS",
        default=True,
    )
    notify_whatsapp = fields.Boolean(
        string="Notify by WhatsApp",
        default=True,
        help="Uses the WhatsApp hook when a provider is configured; "
             "otherwise falls back to SMS when SMS is enabled.",
    )
    notification_message = fields.Text(
        string="Notification Message",
        translate=True,
        default=(
            "Dear {partner_name}, you received {cashback_amount} SAR cashback "
            "on invoice {invoice_name}. Your new wallet balance is {wallet_balance} SAR."
        ),
        help="Placeholders: {partner_name}, {cashback_amount}, {invoice_name}, "
             "{wallet_balance}, {percentage}",
    )

    @api.constrains("date_start", "date_end")
    def _check_dates(self):
        for program in self:
            if program.date_start and program.date_end and program.date_start > program.date_end:
                raise ValidationError(_("Cashback end date must be on or after the start date."))

    @api.constrains("percentage")
    def _check_percentage(self):
        for program in self:
            if program.percentage <= 0:
                raise ValidationError(_("Cashback percentage must be greater than zero."))

    @api.model
    def _get_active_program(self, company, on_date=None):
        """Return the active program for company on a given date (today by default)."""
        on_date = on_date or fields.Date.context_today(self)
        return self.search(
            [
                ("active", "=", True),
                ("company_id", "=", company.id),
                ("date_start", "<=", on_date),
                ("date_end", ">=", on_date),
            ],
            limit=1,
            order="date_start desc, id desc",
        )

    def _format_notification_message(self, partner, invoice, cashback_amount, wallet_balance):
        self.ensure_one()
        template = self.notification_message or ""
        return template.format(
            partner_name=partner.name or "",
            cashback_amount="%.2f" % cashback_amount,
            invoice_name=invoice.name or "",
            wallet_balance="%.2f" % wallet_balance,
            percentage="%.2f" % self.percentage,
        )
