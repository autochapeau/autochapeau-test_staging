from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools import float_compare


class SaleOrder(models.Model):
    _inherit = "sale.order"

    discount_max_percent = fields.Float(
        string="Max Line Discount (%)",
        compute="_compute_discount_approval_flags",
        store=True,
    )
    discount_approval_required = fields.Boolean(
        string="Discount Approval Required",
        compute="_compute_discount_approval_flags",
        store=True,
    )
    discount_approved = fields.Boolean(
        string="Discount Approved",
        copy=False,
        readonly=True,
    )
    discount_approved_by_id = fields.Many2one(
        "res.users",
        string="Discount Approved By",
        copy=False,
        readonly=True,
    )
    discount_approved_percent = fields.Float(
        string="Approved Max Discount (%)",
        copy=False,
        readonly=True,
    )
    can_approve_discount = fields.Boolean(
        string="Can Approve Discount",
        compute="_compute_can_approve_discount",
    )

    @api.depends(
        "order_line.discount",
        "order_line.display_type",
        "order_line.product_id",
        "order_line.price_unit",
        "order_line.product_uom_qty",
        "user_id",
    )
    def _compute_discount_approval_flags(self):
        for order in self:
            max_discount = order._get_max_line_discount_percent()
            salesperson = order.user_id
            limit = (
                salesperson._get_max_sale_discount_percent()
                if salesperson
                else 0.0
            )
            order.discount_max_percent = max_discount
            order.discount_approval_required = (
                float_compare(max_discount, limit, precision_digits=2) > 0
            )

    @api.depends(
        "discount_approval_required",
        "discount_max_percent",
        "discount_approved",
        "state",
    )
    def _compute_can_approve_discount(self):
        approver_limit = self.env.user._get_max_sale_discount_percent()
        for order in self:
            order.can_approve_discount = (
                order.state in ("draft", "sent")
                and order.discount_approval_required
                and not order.discount_approved
                and float_compare(
                    approver_limit,
                    order.discount_max_percent,
                    precision_digits=2,
                ) >= 0
            )

    def _get_max_line_discount_percent(self):
        self.ensure_one()
        max_discount = 0.0
        base_amount = 0.0
        percent_money = 0.0
        amount_discount = 0.0

        for line in self.order_line:
            if line._sale_discount_limit_skip():
                continue
            if line._sale_discount_limit_is_amount_line():
                amount_discount += abs(line._sale_discount_limit_base_amount())
                continue

            line_base = line._sale_discount_limit_base_amount()
            line_percent = line.discount or 0.0
            base_amount += line_base
            percent_money += line_base * line_percent / 100.0
            if float_compare(line_percent, max_discount, precision_digits=2) > 0:
                max_discount = line_percent

        if float_compare(base_amount, 0.0, precision_digits=2) > 0:
            combined = (percent_money + amount_discount) / base_amount * 100.0
            if float_compare(combined, max_discount, precision_digits=2) > 0:
                max_discount = combined
        elif float_compare(amount_discount, 0.0, precision_digits=2) > 0:
            max_discount = 100.0

        return max_discount

    def _reset_discount_approval(self):
        orders = self.filtered(
            lambda order: order.discount_approved
            and order.state in ("draft", "sent")
        )
        if not orders:
            return
        orders.write({
            "discount_approved": False,
            "discount_approved_by_id": False,
            "discount_approved_percent": 0.0,
        })

    def write(self, vals):
        res = super().write(vals)
        if "user_id" in vals:
            self.filtered(
                lambda order: order.state in ("draft", "sent")
            )._reset_discount_approval()
        return res

    def action_approve_discount(self):
        for order in self:
            if order.state not in ("draft", "sent"):
                raise UserError(_(
                    "Discount approval is only available on draft quotations."
                ))
            if not order.discount_approval_required:
                raise UserError(_(
                    "This order does not require discount approval."
                ))
            if order.discount_approved:
                raise UserError(_("This order discount is already approved."))
            approver_limit = self.env.user._get_max_sale_discount_percent()
            if float_compare(
                approver_limit,
                order.discount_max_percent,
                precision_digits=2,
            ) < 0:
                raise UserError(_(
                    "You cannot approve this discount.\n"
                    "Order maximum discount: %(max)s%%\n"
                    "Your approval limit: %(limit)s%%",
                    max=order.discount_max_percent,
                    limit=approver_limit,
                ))
            order.write({
                "discount_approved": True,
                "discount_approved_by_id": self.env.user.id,
                "discount_approved_percent": order.discount_max_percent,
            })
            salesperson_limit = (
                order.user_id._get_max_sale_discount_percent()
                if order.user_id
                else 0.0
            )
            order.message_post(
                body=_(
                    "Discount approved by %(approver)s.\n"
                    "Salesperson limit: %(sales_limit)s%%\n"
                    "Order maximum discount: %(max)s%%\n"
                    "Approver limit: %(approver_limit)s%%",
                    approver=self.env.user.display_name,
                    sales_limit=salesperson_limit,
                    max=order.discount_max_percent,
                    approver_limit=approver_limit,
                ),
                subtype_xmlid="mail.mt_note",
            )
        return True

    def action_confirm(self):
        for order in self:
            if (
                order.discount_approval_required
                and not order.discount_approved
            ):
                salesperson_limit = (
                    order.user_id._get_max_sale_discount_percent()
                    if order.user_id
                    else 0.0
                )
                raise UserError(_(
                    "Cannot confirm this order until the discount is approved.\n"
                    "Salesperson: %(user)s (limit %(limit)s%%)\n"
                    "Maximum line discount: %(max)s%%\n"
                    "A user with at least %(max)s%% approval limit must "
                    "approve the discount first.",
                    user=order.user_id.display_name if order.user_id else "-",
                    limit=salesperson_limit,
                    max=order.discount_max_percent,
                ))
        return super().action_confirm()
