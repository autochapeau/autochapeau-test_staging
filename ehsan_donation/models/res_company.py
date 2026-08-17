from odoo import fields, models


class ResCompany(models.Model):
    _inherit = "res.company"

    ehsan_company_donation_enabled = fields.Boolean(
        string="Company Ehsan Donation",
        default=True,
        help="Automatically donate when paid untaxed invoice amounts of a sale reach the threshold.",
    )
    ehsan_company_donation_threshold = fields.Monetary(
        string="Invoice Threshold",
        currency_field="currency_id",
        default=1000.0,
        help="Minimum paid untaxed invoice total that triggers a company donation.",
    )
    ehsan_company_donation_amount = fields.Monetary(
        string="Company Donation Amount",
        currency_field="currency_id",
        default=10.0,
        help="Amount the company donates per qualifying invoice.",
    )


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    ehsan_company_donation_enabled = fields.Boolean(
        related="company_id.ehsan_company_donation_enabled",
        readonly=False,
    )
    ehsan_company_donation_threshold = fields.Monetary(
        related="company_id.ehsan_company_donation_threshold",
        readonly=False,
    )
    ehsan_company_donation_amount = fields.Monetary(
        related="company_id.ehsan_company_donation_amount",
        readonly=False,
    )
