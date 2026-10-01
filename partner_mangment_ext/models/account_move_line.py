from odoo import api, fields, models
from odoo.tools import frozendict


class AccountMoveLine(models.Model):
    _inherit = "account.move.line"

    discount_type = fields.Selection(
        [
            ("percent", "Percentage"),
            ("amount", "Amount"),
        ],
        string="Discount Type",
        default="percent",
        copy=True,
    )
    discount_amount = fields.Monetary(
        string="Discount Amount",
        currency_field="currency_id",
        copy=True,
    )

    def _is_product_discount_line(self):
        """SO uses falsy display_type; invoices use display_type='product'."""
        self.ensure_one()
        return self.display_type in (False, "product")

    def _uses_amount_discount(self):
        self.ensure_one()
        if not self._is_product_discount_line():
            return False
        if self.discount_type != "amount":
            return False
        if (self.discount_amount or 0.0) > 0:
            return True
        if "sale_line_ids" not in self._fields:
            return False
        return bool(
            self.sale_line_ids.filtered(
                lambda sol: sol.discount_type == "amount" and sol.discount_amount
            )
        )

    def _amount_discount_net_price_unit(self):
        """Unit price after exact fixed discount for invoice computation."""
        self.ensure_one()
        qty = self.quantity or 0.0
        if not qty:
            return self.price_unit or 0.0
        amount = self.discount_amount or 0.0
        if amount <= 0 and "sale_line_ids" in self._fields:
            sale_line = self.sale_line_ids.filtered(
                lambda sol: sol.discount_type == "amount" and sol.discount_amount
            )[:1]
            if sale_line:
                so_qty = sale_line.product_uom_qty or 1.0
                amount = (sale_line.discount_amount or 0.0) * (qty / so_qty)
        base = (self.price_unit or 0.0) * qty
        return max(base - amount, 0.0) / qty

    def _apply_fixed_amount_discount_on_tax_base(self, tax_base):
        """Use exact money discount while keeping Disc.% on the line for display."""
        self.ensure_one()
        if self._uses_amount_discount() and self.quantity:
            tax_base["price_unit"] = self._amount_discount_net_price_unit()
            tax_base["discount"] = 0.0
        return tax_base

    def _prepare_base_line_for_taxes_computation(self, **kwargs):
        self.ensure_one()
        prepare = getattr(super(), "_prepare_base_line_for_taxes_computation", None)
        if not prepare:
            return self._convert_to_tax_base_line_dict(**kwargs)
        return self._apply_fixed_amount_discount_on_tax_base(prepare(**kwargs))

    def _convert_to_tax_base_line_dict(self, **kwargs):
        self.ensure_one()
        parent = super()._convert_to_tax_base_line_dict
        tax_base = parent(**kwargs) if kwargs else parent()
        return self._apply_fixed_amount_discount_on_tax_base(tax_base)

    @api.depends(
        "quantity",
        "discount",
        "price_unit",
        "tax_ids",
        "currency_id",
        "discount_type",
        "discount_amount",
    )
    def _compute_totals(self):
        """Odoo uses Disc.% first; overwrite Amount lines with exact money net."""
        super()._compute_totals()
        for line in self:
            if not line._uses_amount_discount() or line.display_type != "product":
                continue
            net_unit = line._amount_discount_net_price_unit()
            if line.tax_ids:
                taxes_res = line.tax_ids.compute_all(
                    net_unit,
                    quantity=line.quantity,
                    currency=line.currency_id,
                    product=line.product_id,
                    partner=line.partner_id,
                    is_refund=line.is_refund,
                )
                line.price_subtotal = taxes_res["total_excluded"]
                line.price_total = taxes_res["total_included"]
            else:
                line.price_subtotal = line.price_total = (line.quantity or 0.0) * net_unit

    @api.depends(
        "tax_ids",
        "currency_id",
        "partner_id",
        "analytic_distribution",
        "balance",
        "move_id.partner_id",
        "price_unit",
        "quantity",
        "discount",
        "discount_type",
        "discount_amount",
    )
    def _compute_all_tax(self):
        """Tax journal lines use price*(1-disc%); force exact Amount net like SO."""
        amount_lines = self.filtered(
            lambda line: (
                line._uses_amount_discount()
                and line.display_type == "product"
                and line.move_id.is_invoice(True)
            )
        )
        other_lines = self - amount_lines
        if other_lines:
            super(AccountMoveLine, other_lines)._compute_all_tax()

        for line in amount_lines:
            sign = line.move_id.direction_sign
            amount_currency = sign * line._amount_discount_net_price_unit()
            compute_all_currency = line.tax_ids.compute_all(
                amount_currency,
                currency=line.currency_id,
                quantity=line.quantity,
                product=line.product_id,
                partner=line.move_id.partner_id or line.partner_id,
                is_refund=line.is_refund,
                handle_price_include=True,
                include_caba_tags=line.move_id.always_tax_exigible,
                fixed_multiplicator=sign,
            )
            rate = (
                line.amount_currency / line.balance
                if (line.amount_currency and line.balance)
                else line.currency_rate
            )
            line.compute_all_tax_dirty = True
            line.compute_all_tax = {
                frozendict(
                    {
                        "tax_repartition_line_id": tax["tax_repartition_line_id"],
                        "group_tax_id": tax["group"] and tax["group"].id or False,
                        "account_id": tax["account_id"] or line.account_id.id,
                        "currency_id": line.currency_id.id,
                        "analytic_distribution": (
                            tax["analytic"] or not tax["use_in_tax_closing"]
                        )
                        and line.analytic_distribution,
                        "tax_ids": [(6, 0, tax["tax_ids"])],
                        "tax_tag_ids": [(6, 0, tax["tag_ids"])],
                        "partner_id": line.move_id.partner_id.id or line.partner_id.id,
                        "move_id": line.move_id.id,
                        "display_type": line.display_type,
                    }
                ): {
                    "name": tax["name"],
                    "balance": tax["amount"] / rate,
                    "amount_currency": tax["amount"],
                    "tax_base_amount": tax["base"]
                    / rate
                    * (-1 if line.tax_tag_invert else 1),
                }
                for tax in compute_all_currency["taxes"]
                if tax["amount"]
            }
            if not line.tax_repartition_line_id:
                line.compute_all_tax[frozendict({"id": line.id})] = {
                    "tax_tag_ids": [(6, 0, compute_all_currency["base_tags"])],
                }

    @api.onchange("discount_type", "discount_amount", "price_unit", "quantity")
    def _onchange_invoice_amount_discount(self):
        for line in self:
            if not line._is_product_discount_line() or line.discount_type != "amount":
                continue
            qty = line.quantity or 0.0
            base = (line.price_unit or 0.0) * qty
            if not base:
                line.discount = 0.0
                continue
            line.discount = min(100.0, (line.discount_amount or 0.0) / base * 100.0)
