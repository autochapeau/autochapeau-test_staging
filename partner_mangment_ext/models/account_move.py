from collections import defaultdict

from odoo import _, api, models
from odoo.exceptions import UserError
from odoo.tools import float_is_zero
from odoo.tools.misc import formatLang


class AccountMove(models.Model):
    _inherit = "account.move"

    def _has_amount_discount_invoice_lines(self):
        self.ensure_one()
        return any(
            line._uses_amount_discount()
            for line in self.invoice_line_ids
            if line.display_type == "product"
        )

    def _prepare_product_base_line_for_taxes_computation(self, product_line):
        """Keep displayed Disc.% but compute taxes from exact Amount discount."""
        self.ensure_one()
        parent = getattr(
            super(),
            "_prepare_product_base_line_for_taxes_computation",
            None,
        )
        if parent:
            base_line = parent(product_line)
        else:
            base_line = product_line._convert_to_tax_base_line_dict()
        apply = getattr(product_line, "_apply_fixed_amount_discount_on_tax_base", None)
        if apply:
            return apply(base_line)
        return base_line

    def _align_tax_totals_with_invoice_line_totals(self):
        """Ignore stale tax journal lines; match widget to exact line price_total."""
        self.ensure_one()
        if not self.tax_totals or not self.is_invoice(include_receipts=True):
            return
        if not self._has_amount_discount_invoice_lines():
            return

        product_lines = self.invoice_line_ids.filtered(
            lambda line: line.display_type == "product"
        )
        currency = self.currency_id or self.company_id.currency_id
        amount_untaxed = currency.round(sum(product_lines.mapped("price_subtotal")))
        amount_total = currency.round(sum(product_lines.mapped("price_total")))
        amount_tax = currency.round(amount_total - amount_untaxed)

        totals = self.tax_totals
        old_tax = sum(
            group["tax_group_amount"]
            for groups in (totals.get("groups_by_subtotal") or {}).values()
            for group in groups
        )
        if (
            currency.is_zero(amount_total - totals.get("amount_total", 0.0))
            and currency.is_zero(amount_untaxed - totals.get("amount_untaxed", 0.0))
            and currency.is_zero(amount_tax - old_tax)
        ):
            return

        totals["amount_untaxed"] = amount_untaxed
        totals["amount_total"] = amount_total
        totals["formatted_amount_untaxed"] = formatLang(
            self.env, amount_untaxed, currency_obj=currency
        )
        totals["formatted_amount_total"] = formatLang(
            self.env, amount_total, currency_obj=currency
        )

        delta = amount_tax - old_tax
        adjusted = False
        for groups in (totals.get("groups_by_subtotal") or {}).values():
            for group in groups:
                group["tax_group_amount"] = currency.round(
                    group["tax_group_amount"] + (delta if not adjusted else 0.0)
                )
                group["formatted_tax_group_amount"] = formatLang(
                    self.env, group["tax_group_amount"], currency_obj=currency
                )
                if not adjusted:
                    group["tax_group_base_amount"] = amount_untaxed
                    group["formatted_tax_group_base_amount"] = formatLang(
                        self.env, amount_untaxed, currency_obj=currency
                    )
                    adjusted = True

        if len(totals.get("subtotals") or []) == 1:
            totals["subtotals"][0]["amount"] = amount_untaxed
            totals["subtotals"][0]["formatted_amount"] = formatLang(
                self.env, amount_untaxed, currency_obj=currency
            )

        self.tax_totals = totals

    @api.depends_context("lang")
    @api.depends(
        "invoice_line_ids.currency_rate",
        "invoice_line_ids.tax_base_amount",
        "invoice_line_ids.tax_line_id",
        "invoice_line_ids.price_total",
        "invoice_line_ids.price_subtotal",
        "invoice_line_ids.discount_type",
        "invoice_line_ids.discount_amount",
        "invoice_payment_term_id",
        "partner_id",
        "currency_id",
    )
    def _compute_tax_totals(self):
        super()._compute_tax_totals()
        for move in self:
            move._align_tax_totals_with_invoice_line_totals()

    def _get_sale_orders_for_discount_fix(self):
        """Find related sale orders via invoice_ids, line links, or origin."""
        self.ensure_one()
        orders = self.env["sale.order"].search([("invoice_ids", "in", self.ids)])
        if orders:
            return orders
        orders = self.invoice_line_ids.sale_line_ids.order_id
        if orders:
            return orders
        origin = (self.invoice_origin or "").strip()
        if not origin:
            return self.env["sale.order"]
        names = [
            name.strip()
            for name in origin.replace(";", ",").split(",")
            if name.strip()
        ]
        if not names:
            return self.env["sale.order"]
        return self.env["sale.order"].search([("name", "in", names)])

    def _invoice_lines_to_preserve_on_so_rebuild(self):
        """Keep non-SO technical lines (e.g. Ehsan donation) when rebuilding."""
        self.ensure_one()
        return self.invoice_line_ids.filtered(
            lambda line: (
                "ehsan_donation_sale_order_id" in line._fields
                and line.ehsan_donation_sale_order_id
            )
        )

    def action_fix_amount_discounts_from_sale(self):
        """Rebuild draft invoice product lines from the related sale order(s)."""
        self.ensure_one()
        if self.state != "draft":
            raise UserError(_(
                "Discount fix is only allowed on draft invoices."
            ))
        if self.move_type not in ("out_invoice", "out_refund"):
            raise UserError(_(
                "This action is only available on customer invoices/credit notes."
            ))

        sale_orders = self._get_sale_orders_for_discount_fix()
        if not sale_orders:
            raise UserError(_(
                "No related sale order was found for this invoice."
            ))

        qty_by_sol = defaultdict(float)
        sols_on_invoice = self.env["sale.order.line"]
        for inv_line in self.invoice_line_ids:
            for sol in inv_line.sale_line_ids:
                qty_by_sol[sol.id] += inv_line.quantity
                sols_on_invoice |= sol

        if not sols_on_invoice:
            sols_on_invoice = sale_orders.order_line

        preserve_lines = self._invoice_lines_to_preserve_on_so_rebuild()
        lines_to_remove = self.invoice_line_ids - preserve_lines
        if lines_to_remove:
            lines_to_remove.unlink()

        new_line_commands = []
        rebuilt = 0
        for sol in sols_on_invoice.sorted(
            lambda line: (line.order_id.id, line.sequence, line.id)
        ):
            if sol.display_type in ("line_section", "line_note"):
                vals = sol._prepare_invoice_line()
                new_line_commands.append((0, 0, vals))
                rebuilt += 1
                continue

            if sol.id in qty_by_sol:
                quantity = qty_by_sol[sol.id]
            else:
                quantity = sol.qty_to_invoice
            if float_is_zero(
                quantity, precision_rounding=sol.product_uom.rounding or 0.01
            ):
                continue

            vals = sol._prepare_invoice_line(quantity=quantity)
            new_line_commands.append((0, 0, vals))
            rebuilt += 1

        if not new_line_commands:
            raise UserError(_(
                "No sale order lines could be rebuilt on this invoice."
            ))

        self.write({"invoice_line_ids": new_line_commands})
        self.invoice_line_ids._compute_totals()
        if hasattr(self.invoice_line_ids, "_compute_all_tax"):
            self.invoice_line_ids._compute_all_tax()
        self.invalidate_recordset(["tax_totals"])
        self._compute_tax_totals()
        if hasattr(self, "_sync_draft_invoice_accounting"):
            self._sync_draft_invoice_accounting()

        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Invoice lines rebuilt"),
                "message": _(
                    "%(count)s line(s) were rebuilt from the sale order "
                    "with exact discount amounts."
                )
                % {"count": rebuilt},
                "type": "success",
                "sticky": False,
                "next": {"type": "ir.actions.client", "tag": "reload"},
            },
        }
