from odoo import fields, models


class ResUsers(models.Model):
    _inherit = "res.users"

    can_edit_existing_contacts = fields.Boolean(
        string="Allow editing existing contacts",
        help="Allows this user to save changes to existing contacts within their current access rights. "
        "The user's existing permissions determine whether they can create contacts.",
        groups="base.group_system",
    )
