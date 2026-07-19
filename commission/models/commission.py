from odoo import _, api, exceptions, fields, models


class Commission(models.Model):
    _name = "commission"
    _description = "Commission"

    name = fields.Char(required=True)
    job_target_ids = fields.One2many("commission.target.job", "commission_id")
    employee_target_ids = fields.One2many("commission.target.employee", "commission_id")
    section_ids = fields.One2many(
        string="Sections",
        comodel_name="commission.section",
        inverse_name="commission_id",
    )
    discount_section_ids = fields.One2many(
        string="Discount Sections",
        comodel_name="commission.discount.section",
        inverse_name="commission_id",
    )
    active = fields.Boolean(default=True)


class CommissionSection(models.Model):
    _name = "commission.section"
    _description = "Commission section"

    commission_id = fields.Many2one("commission", string="Commission")

    commission_category_id = fields.Many2one("commission.category", required=True)
    amount_from = fields.Float(string="From")
    amount_to = fields.Float(string="To")
    percent = fields.Float(required=True)

    @api.constrains("amount_from", "amount_to")
    def _check_amounts(self):
        for section in self:
            if section.amount_to < section.amount_from:
                raise exceptions.ValidationError(_("The lower limit cannot be greater than upper one."))


class CommissionDiscountSection(models.Model):
    _name = "commission.discount.section"
    _description = "Commission discount section"

    commission_id = fields.Many2one("commission", string="Commission")

    amount_from = fields.Float(string="From")
    amount_to = fields.Float(string="To")
    deduction_percent = fields.Float(required=True)

    @api.constrains("amount_from", "amount_to")
    def _check_amounts(self):
        for section in self:
            if section.amount_to < section.amount_from:
                raise exceptions.ValidationError(_("The lower limit cannot be greater than upper one."))
