from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


class SaleMultiSplitPaymentWizard(models.TransientModel):
    _name = "sale.multi.split.payment.wizard"
    _description = "Collect Payment for Multiple Sale Orders"

    sale_order_ids = fields.Many2many(
        "sale.order",
        string="Sale Orders",
        required=True,
        readonly=True,
    )
    partner_id = fields.Many2one(
        "res.partner",
        string="Customer",
        compute="_compute_order_details",
        readonly=True,
    )
    company_id = fields.Many2one(
        "res.company",
        compute="_compute_order_details",
        readonly=True,
    )
    currency_id = fields.Many2one(
        "res.currency",
        compute="_compute_order_details",
        readonly=True,
    )
    total_remaining = fields.Monetary(
        string="Total Remaining",
        compute="_compute_order_details",
        currency_field="currency_id",
        readonly=True,
    )
    collection_method_id = fields.Many2one(
        "sale.collection.method",
        string="Payment Method",
        required=True,
        domain=(
            "[('company_id', '=', company_id), ('active', '=', True), "
            "('processing_type', '=', 'manual')]"
        ),
        check_company=True,
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
        help="Optional bank transfer / cheque / cash receipt reference.",
    )

    @api.depends(
        "sale_order_ids",
        "sale_order_ids.partner_id",
        "sale_order_ids.company_id",
        "sale_order_ids.currency_id",
        "sale_order_ids.split_amount_remaining",
    )
    def _compute_order_details(self):
        for wizard in self:
            orders = wizard.sale_order_ids
            wizard.partner_id = orders[:1].partner_id
            wizard.company_id = orders[:1].company_id
            wizard.currency_id = orders[:1].currency_id
            wizard.total_remaining = sum(orders.mapped("split_amount_remaining"))

    @api.model
    def default_get(self, field_list):
        values = super().default_get(field_list)
        order_commands = values.get("sale_order_ids") or self.env.context.get(
            "default_sale_order_ids"
        )
        orders = self.env["sale.order"]
        if order_commands:
            if isinstance(order_commands, list) and order_commands:
                if isinstance(order_commands[0], (tuple, list)):
                    orders = self.env["sale.order"].browse(order_commands[0][2])
                else:
                    orders = self.env["sale.order"].browse(order_commands)
        if not orders:
            orders = self.env["sale.order"].browse(
                self.env.context.get("active_ids", [])
            )
            if orders and "sale_order_ids" in field_list:
                values["sale_order_ids"] = [(6, 0, orders.ids)]
        if orders:
            self._validate_orders(orders)
            if "amount" in field_list and not values.get("amount"):
                values["amount"] = sum(orders.mapped("split_amount_remaining"))
            if "collection_method_id" in field_list and not values.get(
                "collection_method_id"
            ):
                method = self.env["sale.collection.method"].search(
                    [
                        ("company_id", "=", orders[0].company_id.id),
                        ("active", "=", True),
                        ("processing_type", "=", "manual"),
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
            if wizard.currency_id and wizard.currency_id.compare_amounts(
                wizard.amount, wizard.total_remaining
            ) > 0:
                raise ValidationError(
                    _("The entered amount exceeds the selected orders' total remaining.")
                )

    @api.model
    def _validate_orders(self, orders):
        if not orders:
            raise UserError(_("Please select at least one sale order."))
        invalid_orders = orders.filtered(
            lambda order: order.state not in ("sale", "done")
            or order.currency_id.is_zero(order.split_amount_remaining)
        )
        if invalid_orders:
            raise UserError(
                _(
                    "Only confirmed sale orders with a remaining amount can be selected."
                )
            )
        if len(orders.mapped("partner_id")) != 1:
            raise UserError(_("All selected sale orders must belong to the same customer."))
        if len(orders.mapped("company_id")) != 1:
            raise UserError(_("All selected sale orders must belong to the same company."))
        if len(orders.mapped("currency_id")) != 1:
            raise UserError(_("All selected sale orders must use the same currency."))

    def action_collect_payment(self):
        self.ensure_one()
        orders = self.sale_order_ids.exists()
        self._validate_orders(orders)
        if self.collection_method_id.processing_type != "manual":
            raise UserError(
                _(
                    "Multi-order collection currently supports manual payment methods only."
                )
            )
        journal = self.journal_id or self.collection_method_id.resolve_journal()
        if not journal:
            raise UserError(
                _("Please configure a journal on the selected payment method.")
            )
        method_line = self.collection_method_id.get_payment_method_line(journal)
        if not method_line:
            raise UserError(
                _(
                    "Journal %s has no inbound payment method configured."
                )
                % journal.display_name
            )
        if self.require_reference and not self.provider_reference:
            raise UserError(_("Please enter the payment reference."))

        total_remaining = sum(orders.mapped("split_amount_remaining"))
        if self.currency_id.compare_amounts(self.amount, total_remaining) > 0:
            raise ValidationError(
                _("The entered amount exceeds the selected orders' total remaining.")
            )

        amount_left = self.amount
        ordered_orders = orders.sorted(
            key=lambda order: (order.date_order or fields.Datetime.now(), order.id)
        )
        allocation_values = []
        for order in ordered_orders:
            if self.currency_id.is_zero(amount_left):
                break
            allocation_amount = min(amount_left, order.split_amount_remaining)
            allocation_values.append(
                {
                    "sale_order_id": order.id,
                    "collection_method_id": self.collection_method_id.id,
                    "amount": allocation_amount,
                    "journal_id": journal.id,
                    "provider_reference": self.provider_reference,
                }
            )
            amount_left -= allocation_amount

        reference_bits = [
            _("Multi-order payment"),
            ", ".join(ordered_orders.mapped("name")),
        ]
        if self.provider_reference:
            reference_bits.append(self.provider_reference)
        account_payment = self.env["account.payment"].sudo().create(
            {
                "payment_type": "inbound",
                "partner_type": "customer",
                "partner_id": self.partner_id.id,
                "amount": self.amount,
                "currency_id": self.currency_id.id,
                "date": fields.Date.context_today(self),
                "journal_id": journal.id,
                "payment_method_line_id": method_line.id,
                "ref": " / ".join(reference_bits),
            }
        )
        account_payment.sudo().action_post()

        for values in allocation_values:
            values.update(
                {
                    "state": "paid",
                    "provider_status": _("Manual payment received"),
                    "account_payment_id": account_payment.id,
                }
            )
        allocations = self.env["sale.order.payment"].create(allocation_values)
        allocations._reconcile_available_invoices()

        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Payment posted"),
                "message": _(
                    "%(amount).2f %(currency)s was allocated across %(count)s sale orders."
                )
                % {
                    "amount": self.amount,
                    "currency": self.currency_id.name,
                    "count": len(allocations),
                },
                "type": "success",
                "sticky": False,
                "next": {"type": "ir.actions.act_window_close"},
            },
        }
