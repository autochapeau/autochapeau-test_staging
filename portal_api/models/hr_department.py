from odoo import fields, models


class HrDepartment(models.Model):
    _inherit = "hr.department"

    show_on_website = fields.Boolean(
        string="Show on Website",
        default=False,
    )
