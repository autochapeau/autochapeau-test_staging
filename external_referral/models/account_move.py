from odoo import fields, models


class AccountMove(models.Model):
    _inherit = "account.move"

    external_referral_ids = fields.One2many(
        "external.referral",
        "invoice_id",
        string="External Referrals",
        copy=False,
    )
    external_referral_count = fields.Integer(
        string="External Referral Count",
        compute="_compute_external_referrals",
    )
    external_referral_total = fields.Monetary(
        string="Referral Amount",
        currency_field="currency_id",
        compute="_compute_external_referrals",
    )

    def _compute_external_referrals(self):
        for invoice in self:
            active_referrals = invoice.external_referral_ids.filtered(
                lambda referral: referral.state != "cancelled"
            )
            invoice.external_referral_count = len(active_referrals)
            invoice.external_referral_total = sum(active_referrals.mapped("amount"))

    def _invoice_paid_hook(self):
        res = super()._invoice_paid_hook()
        self.env["external.referral"]._sync_paid_invoices(self)
        return res

    def button_draft(self):
        res = super().button_draft()
        self.env["external.referral"]._cancel_open_for_invoices(self)
        return res

    def button_cancel(self):
        res = super().button_cancel()
        self.env["external.referral"]._cancel_open_for_invoices(self)
        return res

    def action_view_external_referrals(self):
        self.ensure_one()
        action = self.env["ir.actions.actions"]._for_xml_id(
            "external_referral.action_external_referral"
        )
        action["domain"] = [("invoice_id", "=", self.id)]
        action["context"] = {"default_invoice_id": self.id}
        return action
