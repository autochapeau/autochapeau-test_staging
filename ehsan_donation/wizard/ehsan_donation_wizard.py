from odoo import _, api, fields, models
from odoo.exceptions import UserError


class EhsanDonationWizard(models.TransientModel):
    _name = "ehsan.donation.wizard"
    _description = "Ehsan Donation Wizard"

    sale_order_id = fields.Many2one(
        "sale.order",
        string="Sales Order",
        required=True,
        readonly=True,
    )
    currency_id = fields.Many2one(
        related="sale_order_id.currency_id",
        readonly=True,
    )
    donation_amount = fields.Monetary(
        string="Donation Amount",
        currency_field="currency_id",
        required=True,
    )
    preset_amount = fields.Selection(
        selection=[
            ("10", "10"),
            ("20", "20"),
            ("50", "50"),
            ("100", "100"),
            ("custom", "Custom"),
        ],
        string="Preset",
        default="10",
    )

    @api.onchange("preset_amount")
    def _onchange_preset_amount(self):
        if self.preset_amount and self.preset_amount != "custom":
            self.donation_amount = float(self.preset_amount)

    def action_confirm(self):
        self.ensure_one()
        order = self.sale_order_id
        if order.order_type == "contract":
            raise UserError(_(
                "Ehsan donations are not available on Contract sale orders."
            ))
        if order.ehsan_donation_move_id:
            raise UserError(
                _(
                    "An Ehsan donation journal entry already exists for this order."
                )
            )
        # Readonly monetary values are not always sent from the client; trust preset.
        if self.preset_amount and self.preset_amount != "custom":
            amount = float(self.preset_amount)
        else:
            amount = self.donation_amount or 0.0
        if amount < 0:
            raise UserError(_("Donation amount cannot be negative."))
        order.write(
            {
                "ehsan_donation_amount": amount,
                "ehsan_donation_declined": False,
            }
        )
        return {"type": "ir.actions.act_window_close"}

    def action_decline(self):
        self.ensure_one()
        order = self.sale_order_id
        if order.ehsan_donation_move_id:
            raise UserError(
                _(
                    "An Ehsan donation journal entry already exists for this order."
                )
            )
        order.write(
            {
                "ehsan_donation_amount": 0.0,
                "ehsan_donation_declined": True,
            }
        )
        return {"type": "ir.actions.act_window_close"}
