from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class SaleOrder(models.Model):
    _inherit = "sale.order"

    external_referral_percent = fields.Float(
        string="Referral (%)",
        digits=(5, 2),
        copy=False,
        readonly=True,
        help="Percentage copied from the selected agency salesperson.",
    )
    external_referral_expected_amount = fields.Monetary(
        string="Expected Referral Amount",
        currency_field="currency_id",
        compute="_compute_external_referral_expected_amount",
        store=True,
    )
    external_referral_ids = fields.One2many(
        "external.referral",
        "sale_order_id",
        string="External Referrals",
        copy=False,
    )
    external_referral_count = fields.Integer(
        string="External Referral Count",
        compute="_compute_external_referral_totals",
    )
    external_referral_total = fields.Monetary(
        string="Actual Referral Amount",
        currency_field="currency_id",
        compute="_compute_external_referral_totals",
    )

    @api.depends(
        "amount_untaxed",
        "external_referral_percent",
        "order_type",
    )
    def _compute_external_referral_expected_amount(self):
        for order in self:
            if order.order_type == "extern":
                order.external_referral_expected_amount = (
                    order.amount_untaxed
                    * order.external_referral_percent
                    / 100
                )
            else:
                order.external_referral_expected_amount = 0

    @api.depends(
        "external_referral_ids",
        "external_referral_ids.amount",
        "external_referral_ids.state",
    )
    def _compute_external_referral_totals(self):
        for order in self:
            active_referrals = order.external_referral_ids.filtered(
                lambda referral: referral.state != "cancelled"
            )
            order.external_referral_count = len(active_referrals)
            order.external_referral_total = sum(active_referrals.mapped("amount"))

    @api.onchange("agency_salesperson_id", "order_type")
    def _onchange_external_referral_percent(self):
        for order in self:
            order.external_referral_percent = (
                order.agency_salesperson_id.external_referral_percent
                if order.order_type == "extern" and order.agency_salesperson_id
                else 0
            )

    @api.model_create_multi
    def create(self, vals_list):
        Partner = self.env["res.partner"]
        for vals in vals_list:
            if vals.get("order_type") == "extern":
                salesperson = Partner.browse(vals.get("agency_salesperson_id"))
                vals["external_referral_percent"] = (
                    salesperson.external_referral_percent
                )
            else:
                vals["external_referral_percent"] = 0
        return super().create(vals_list)

    def write(self, vals):
        res = super().write(vals)
        if {"order_type", "agency_salesperson_id"} & set(vals):
            for order in self:
                percentage = (
                    order.agency_salesperson_id.external_referral_percent
                    if order.order_type == "extern" and order.agency_salesperson_id
                    else 0
                )
                if order.external_referral_percent != percentage:
                    super(SaleOrder, order).write({
                        "external_referral_percent": percentage,
                    })
        return res

    @api.constrains(
        "order_type",
        "agency_id",
        "agency_salesperson_id",
        "external_referral_percent",
    )
    def _check_external_referral_data(self):
        for order in self:
            if order.order_type != "extern":
                continue
            if (
                order.agency_id
                and order.agency_salesperson_id
                and order.agency_salesperson_id.parent_id != order.agency_id
            ):
                raise ValidationError(_(
                    "The agency salesperson must belong to the selected agency."
                ))
            if not 0 <= order.external_referral_percent <= 100:
                raise ValidationError(_(
                    "Referral percentage must be between 0%% and 100%%."
                ))

    def action_confirm(self):
        for order in self:
            if order.order_type != "extern":
                continue
            if not order.agency_id:
                raise ValidationError(_(
                    "Please select the referring agency before confirming "
                    "an Extern sale order."
                ))
            if not order.agency_salesperson_id:
                raise ValidationError(_(
                    "Please select the agency salesperson before confirming "
                    "an Extern sale order."
                ))
            order.external_referral_percent = (
                order.agency_salesperson_id.external_referral_percent
            )
        return super().action_confirm()

    def action_view_external_referrals(self):
        self.ensure_one()
        action = self.env["ir.actions.actions"]._for_xml_id(
            "external_referral.action_external_referral"
        )
        action["domain"] = [("sale_order_id", "=", self.id)]
        action["context"] = {"default_sale_order_id": self.id}
        return action
