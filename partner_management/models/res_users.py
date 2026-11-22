from odoo import fields, models


class ResUsers(models.Model):
    _inherit = "res.users"

    can_edit_existing_contacts = fields.Boolean(
        string="Allow editing existing contacts",
        help="Allows editing contacts created by other users, within the user's existing access rights. "
        "Users with contact write access can already edit contacts they created themselves.",
        groups="base.group_system",
    )
