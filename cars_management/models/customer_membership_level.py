from odoo import api, fields, models


class CustomerMembershipLevel(models.Model):
    _name = "customer.membership.level"
    _description = "Customer Membership Level"
    _order = "amount_from"

    code = fields.Char(string="Code", required=True,
                       help="Alphanumerical string that represents a unique code")
    name = fields.Char(string="Name", required=True, translate=True)
    amount_from = fields.Float(string="Invoiced Amount From", required=True)
    amount_to = fields.Float(string="Invoiced Amount To", required=True)
    active = fields.Boolean(default=True)
    _sql_constraints = [
        (
            "amount_range_check",
            "CHECK(amount_to >= amount_from)",
            "The 'To' amount must be greater than or equal to the 'From' amount.",
        ),
        (
            "code_unique",
            "unique(code)",
            "The membership code must be unique.",
        ),
    ]

    @api.model_create_multi
    def create(self, vals_list):
        """Auto-generate the code from the name when not provided."""
        for vals in vals_list:
            if not vals.get("code") and vals.get("name"):
                vals["code"] = vals["name"].strip().lower().replace(" ", "_")
        return super().create(vals_list)
