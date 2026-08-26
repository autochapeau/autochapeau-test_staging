from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class SaleOrder(models.Model):
    _inherit = "sale.order"

    commission_autochapeau_amount = fields.Monetary(
        string="Autochapeau Commission Amount",
        currency_field="currency_id",
        copy=False,
    )
    commission_autoflex_amount = fields.Monetary(
        string="Autoflex Commission Amount",
        currency_field="currency_id",
        copy=False,
    )
    commission_autochapeau_base = fields.Monetary(
        string="Autochapeau Untaxed Base",
        currency_field="currency_id",
        compute="_compute_workshop_commission_percent",
        store=True,
    )
    commission_autoflex_base = fields.Monetary(
        string="Autoflex Untaxed Base",
        currency_field="currency_id",
        compute="_compute_workshop_commission_percent",
        store=True,
    )
    commission_autochapeau_percent = fields.Float(
        string="Autochapeau Commission (%)",
        digits=(16, 2),
        compute="_compute_workshop_commission_percent",
        store=True,
    )
    commission_autoflex_percent = fields.Float(
        string="Autoflex Commission (%)",
        digits=(16, 2),
        compute="_compute_workshop_commission_percent",
        store=True,
    )
    commission_agency_total = fields.Monetary(
        string="Total to Pay Agency",
        currency_field="currency_id",
        compute="_compute_commission_agency_total",
        store=True,
        help="Sum of Autochapeau and Autoflex commission amounts.",
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

    @api.depends("commission_autochapeau_amount", "commission_autoflex_amount")
    def _compute_commission_agency_total(self):
        for order in self:
            order.commission_agency_total = (
                order.commission_autochapeau_amount + order.commission_autoflex_amount
            )

    def _get_workshop_untaxed_bases(self):
        """Sum price_subtotal by product workshop commission code."""
        self.ensure_one()
        bases = {"autochapeau": 0.0, "autoflex": 0.0}
        for line in self.order_line:
            if line.display_type in ("line_section", "line_note"):
                continue
            workshop = line.product_id.workshop_id
            code = workshop.code if workshop else False
            if not code:
                name = (workshop.name or "").lower() if workshop else ""
                if "autochapeau" in name:
                    code = "autochapeau"
                elif "autoflex" in name:
                    code = "autoflex"
            if code in bases:
                bases[code] += line.price_subtotal
        return bases

    @api.depends(
        "order_line.price_subtotal",
        "order_line.product_id.workshop_id",
        "order_line.product_id.workshop_id.code",
        "order_line.product_id.workshop_id.name",
        "commission_autochapeau_amount",
        "commission_autoflex_amount",
    )
    def _compute_workshop_commission_percent(self):
        for order in self:
            bases = order._get_workshop_untaxed_bases()
            order.commission_autochapeau_base = bases["autochapeau"]
            order.commission_autoflex_base = bases["autoflex"]
            order.commission_autochapeau_percent = (
                (order.commission_autochapeau_amount / bases["autochapeau"] * 100)
                if bases["autochapeau"]
                else 0.0
            )
            order.commission_autoflex_percent = (
                (order.commission_autoflex_amount / bases["autoflex"] * 100)
                if bases["autoflex"]
                else 0.0
            )

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

    @api.constrains("order_type", "agency_id", "agency_salesperson_id")
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

    def action_confirm(self):
        for order in self:
            if order.order_type != "extern":
                continue
            # if not order.agency_id:
            #     raise ValidationError(_(
            #         "Please select the referring agency before confirming "
            #         "an Extern sale order."
            #     ))
            if not order.agency_salesperson_id:
                raise ValidationError(_(
                    "Please select the agency salesperson before confirming "
                    "an Extern sale order."
                ))
        return super().action_confirm()

    def action_view_external_referrals(self):
        self.ensure_one()
        action = self.env["ir.actions.actions"]._for_xml_id(
            "external_referral.action_external_referral"
        )
        action["domain"] = [("sale_order_id", "=", self.id)]
        action["context"] = {"default_sale_order_id": self.id}
        return action
