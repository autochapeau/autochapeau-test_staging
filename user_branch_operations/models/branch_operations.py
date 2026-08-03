from odoo import api, fields, models


class ResUsers(models.Model):
    _inherit = "res.users"

    branch_id = fields.Many2one(
        "hr.department",
        string="Branch",
        domain="[('department_type', '=', 'branche')]",
        help="Default branch used when this user creates operational records.",
    )


class SaleOrder(models.Model):
    _inherit = "sale.order"

    branch_id = fields.Many2one(
        "hr.department",
        string="Branche",
        domain="[('department_type', '=', 'branche')]",
        default=lambda self: self.env.user.branch_id,
        help="Branch related to the order.",
    )

    def _prepare_invoice(self):
        values = super()._prepare_invoice()
        values["branch_id"] = self.branch_id.id
        return values


class CarAppointment(models.Model):
    _inherit = "car.appointment"

    branch_id = fields.Many2one(
        "hr.department",
        string="Branche",
        domain="[('department_type', '=', 'branche')]",
        default=lambda self: self.env.user.branch_id,
        help="Branch linked to this appointment.",
    )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get("branch_id") and self.env.user.branch_id:
                vals["branch_id"] = self.env.user.branch_id.id
        return super().create(vals_list)


class AccountMove(models.Model):
    _inherit = "account.move"

    branch_id = fields.Many2one(
        "hr.department",
        string="Branch",
        domain="[('department_type', '=', 'branche')]",
        default=lambda self: self.env.user.branch_id,
        help="Branch responsible for this journal entry or invoice.",
    )


class SaleOrderPayment(models.Model):
    _inherit = "sale.order.payment"

    branch_id = fields.Many2one(
        "hr.department",
        related="sale_order_id.branch_id",
        string="Branch",
        store=True,
        index=True,
    )

    def _create_advance_payment(self):
        self.ensure_one()
        payment_record = self.with_context(default_branch_id=self.branch_id.id)
        return super(SaleOrderPayment, payment_record)._create_advance_payment()
