from odoo import models, fields, api
from odoo.exceptions import ValidationError


class HrEmployee(models.Model):
    _inherit = "hr.employee"

    branch_id = fields.Many2one(
        "hr.department",
        string="Branch",
        domain="[('department_type', '=', 'branche')]",
        help="Branch/subsidiary related to the employee",
    )

    @api.constrains('branch_id')
    def _check_branch_is_branche(self):
        for rec in self:
            if rec.branch_id and rec.branch_id.department_type != 'branche':
                raise ValidationError(
                    "The 'Branch' field must reference a department of type 'branche'."
                )

    @api.model_create_multi
    def create(self, vals_list):
        return super().create(vals_list)
