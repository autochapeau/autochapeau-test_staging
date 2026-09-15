from odoo import _, api, fields, models
from odoo.exceptions import ValidationError
from odoo.tools import float_compare, float_round


class SaleOrderLine(models.Model):
    _inherit = "sale.order.line"

    discount_type = fields.Selection(
        [
            ("percent", "Percentage"),
            ("amount", "Amount"),
        ],
        string="Discount Type",
        default="percent",
        required=True,
    )
    discount_amount = fields.Monetary(
        string="Discount Amount",
        currency_field="currency_id",
    )

    def _discount_base_amount(self, price_unit=None, qty=None):
        self.ensure_one()
        unit = self.price_unit if price_unit is None else price_unit
        quantity = self.product_uom_qty if qty is None else qty
        return (unit or 0.0) * (quantity or 0.0)

    def _amount_discount_net_price_unit(self):
        """Unit price after exact fixed discount (avoids % rounding drift)."""
        self.ensure_one()
        qty = self.product_uom_qty or 0.0
        if not qty:
            return self.price_unit or 0.0
        base = self._discount_base_amount()
        net = max(base - (self.discount_amount or 0.0), 0.0)
        return net / qty

    def _apply_fixed_amount_discount_on_tax_base(self, tax_base):
        """Patch tax-base dict so fixed discount is exact money, not rounded %."""
        self.ensure_one()
        if (
            self.discount_type == "amount"
            and not self.display_type
            and self.product_uom_qty
        ):
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
        """Odoo 17: patch result — kwargs price_unit conflicts with parent args."""
        self.ensure_one()
        return self._apply_fixed_amount_discount_on_tax_base(
            super()._convert_to_tax_base_line_dict(**kwargs)
        )

    @api.model
    def _percent_from_amount(self, amount, price_unit, qty):
        base = (price_unit or 0.0) * (qty or 0.0)
        if not base:
            return 0.0
        # Keep extra digits so stored Disc.% stays close to the exact amount.
        digits = max(
            6,
            self.env["decimal.precision"].precision_get("Discount"),
        )
        return float_round(
            min(100.0, (amount or 0.0) / base * 100.0),
            precision_digits=digits,
        )

    @api.model
    def _amount_from_percent(self, percent, price_unit, qty):
        return ((price_unit or 0.0) * (qty or 0.0)) * (percent or 0.0) / 100.0

    @api.model
    def _prepare_discount_vals(self, vals, line=None):
        vals = dict(vals)
        discount_type = vals.get(
            "discount_type",
            line.discount_type if line else "percent",
        )
        price_unit = vals.get("price_unit", line.price_unit if line else 0.0)
        qty = vals.get("product_uom_qty", line.product_uom_qty if line else 0.0)
        if discount_type == "amount":
            amount = vals.get(
                "discount_amount",
                line.discount_amount if line else 0.0,
            )
            vals["discount"] = self._percent_from_amount(amount, price_unit, qty)
        else:
            percent = vals.get("discount", line.discount if line else 0.0)
            vals["discount_amount"] = self._amount_from_percent(
                percent, price_unit, qty
            )
        return vals

    @api.onchange(
        "discount_type",
        "discount_amount",
        "discount",
        "price_unit",
        "product_uom_qty",
    )
    def _onchange_line_discount(self):
        for line in self:
            if line.discount_type == "amount":
                line.discount = self._percent_from_amount(
                    line.discount_amount,
                    line.price_unit,
                    line.product_uom_qty,
                )
            else:
                line.discount_amount = self._amount_from_percent(
                    line.discount,
                    line.price_unit,
                    line.product_uom_qty,
                )

    @api.constrains("discount_amount", "discount_type", "price_unit", "product_uom_qty")
    def _check_discount_amount(self):
        for line in self:
            if line.display_type or line.discount_type != "amount":
                continue
            if float_compare(line.discount_amount or 0.0, 0.0, precision_digits=2) < 0:
                raise ValidationError(_("Discount amount cannot be negative."))
            base = line._discount_base_amount()
            if (
                base
                and float_compare(
                    line.discount_amount or 0.0, base, precision_digits=2
                ) > 0
            ):
                raise ValidationError(_(
                    "Discount amount cannot exceed the order line amount."
                ))

    @api.model_create_multi
    def create(self, vals_list):
        prepared = [self._prepare_discount_vals(vals) for vals in vals_list]
        return super().create(prepared)

    def write(self, vals):
        if self.env.context.get("skip_discount_amount_sync"):
            return super().write(vals)
        watched = {
            "discount_type",
            "discount_amount",
            "discount",
            "price_unit",
            "product_uom_qty",
        }
        if not watched.intersection(vals):
            return super().write(vals)
        result = True
        for line in self:
            result = super(SaleOrderLine, line).write(
                line._prepare_discount_vals(vals, line=line)
            ) and result
        return result
