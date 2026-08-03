from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


class SaleSplitPaymentWizard(models.TransientModel):
    _name = "sale.split.payment.wizard"
    _description = "Collect Sale Order Payment"

    sale_order_id = fields.Many2one(
        "sale.order",
        required=True,
        readonly=True,
    )
    company_id = fields.Many2one(
        related="sale_order_id.company_id",
        readonly=True,
    )
    currency_id = fields.Many2one(
        related="sale_order_id.currency_id",
        readonly=True,
    )
    amount_total = fields.Monetary(
        related="sale_order_id.amount_total",
        currency_field="currency_id",
        readonly=True,
    )
    amount_paid = fields.Monetary(
        related="sale_order_id.split_amount_paid",
        currency_field="currency_id",
        readonly=True,
    )
    amount_pending = fields.Monetary(
        related="sale_order_id.split_amount_pending",
        currency_field="currency_id",
        readonly=True,
    )
    amount_remaining = fields.Monetary(
        related="sale_order_id.split_amount_remaining",
        currency_field="currency_id",
        readonly=True,
    )
    collection_method_id = fields.Many2one(
        "sale.collection.method",
        string="Payment Method",
        required=True,
        domain="[('company_id', '=', company_id), ('active', '=', True)]",
        check_company=True,
    )
    processing_type = fields.Selection(
        related="collection_method_id.processing_type",
        readonly=True,
    )
    require_reference = fields.Boolean(
        related="collection_method_id.require_reference",
        readonly=True,
    )
    amount = fields.Monetary(
        required=True,
        currency_field="currency_id",
    )
    journal_id = fields.Many2one(
        "account.journal",
        domain="[('type', 'in', ('cash', 'bank')), ('company_id', '=', company_id)]",
        check_company=True,
    )
    provider_reference = fields.Char(
        string="Reference",
        help="Optional bank transfer / cheque / POS reference.",
    )

    @api.model
    def default_get(self, field_list):
        values = super().default_get(field_list)
        order = self.env["sale.order"].browse(
            values.get("sale_order_id")
            or self.env.context.get("default_sale_order_id")
        )
        if order:
            if "amount" in field_list and not values.get("amount"):
                values["amount"] = order.split_amount_remaining
            if "collection_method_id" in field_list and not values.get(
                "collection_method_id"
            ):
                method = self.env["sale.collection.method"].search(
                    [
                        ("company_id", "=", order.company_id.id),
                        ("active", "=", True),
                    ],
                    limit=1,
                )
                if method:
                    values["collection_method_id"] = method.id
                    values["journal_id"] = method.resolve_journal().id
        return values

    @api.onchange("collection_method_id")
    def _onchange_collection_method_id(self):
        if self.collection_method_id:
            self.journal_id = self.collection_method_id.resolve_journal()
            if not self.collection_method_id.require_reference:
                self.provider_reference = False

    @api.constrains("amount")
    def _check_amount(self):
        for wizard in self:
            if wizard.amount <= 0:
                raise ValidationError(_("The payment amount must be greater than zero."))
            if wizard.currency_id.compare_amounts(
                wizard.amount, wizard.amount_remaining
            ) > 0:
                raise ValidationError(
                    _(
                        "The entered amount exceeds the remaining amount "
                        "(%(remaining).2f %(currency)s)."
                    )
                    % {
                        "remaining": wizard.amount_remaining,
                        "currency": wizard.currency_id.name,
                    }
                )

    def action_collect_payment(self):
        self.ensure_one()
        if not self.collection_method_id:
            raise UserError(_("Please select a payment method."))
        journal = self.journal_id or self.collection_method_id.resolve_journal()
        if not journal:
            raise UserError(
                _(
                    "Configure a journal on the payment method '%s' "
                    "(Sales > Configuration > Collection Methods)."
                )
                % self.collection_method_id.display_name
            )
        if not self.collection_method_id.get_payment_method_line(journal):
            raise UserError(
                _(
                    "Journal %s has no inbound payment method. Add one under "
                    "Accounting > Configuration > Journals > Incoming Payments."
                )
                % journal.display_name
            )
        if self.require_reference and not self.provider_reference:
            raise UserError(_("Please enter the payment reference."))
        if self.currency_id.compare_amounts(self.amount, self.amount_remaining) > 0:
            raise ValidationError(
                _("The entered amount exceeds the remaining amount.")
            )

        allocation = self.env["sale.order.payment"].create(
            {
                "sale_order_id": self.sale_order_id.id,
                "collection_method_id": self.collection_method_id.id,
                "amount": self.amount,
                "journal_id": journal.id,
                "provider_reference": self.provider_reference,
            }
        )
        try:
            result = allocation.action_process()
        except UserError as error:
            allocation.write(
                {
                    "state": "failed",
                    "error_message": str(error),
                }
            )
            raise

        if isinstance(result, str) and result.startswith("http"):
            return {
                "type": "ir.actions.act_url",
                "url": result,
                "target": "new",
            }

        if allocation.state == "paid" and allocation.account_payment_id:
            return {
                "type": "ir.actions.client",
                "tag": "display_notification",
                "params": {
                    "title": _("Payment posted"),
                    "message": _(
                        "Customer payment %(payment)s was posted and now appears "
                        "on the partner ledger."
                    )
                    % {"payment": allocation.account_payment_id.display_name},
                    "type": "success",
                    "sticky": False,
                    "next": {"type": "ir.actions.act_window_close"},
                },
            }

        return {
            "type": "ir.actions.act_window",
            "name": _("Sale Order Payment"),
            "res_model": "sale.order.payment",
            "res_id": allocation.id,
            "view_mode": "form",
            "views": [(False, "form")],
            "target": "current",
        }
