from odoo import api, fields, models


class ResUsers(models.Model):
    _inherit = "res.users"

    contact_access_mode = fields.Selection(
        selection=[
            ("default", "Default Access"),
            ("own", "Own Contact"),
            ("all", "All Contacts (Manager)"),
        ],
        string="Contact Access",
        compute="_compute_contact_access_mode",
        inverse="_inverse_contact_access_mode",
        required=True,
        groups="base.group_system",
        help="Choose one contact access mode. Default Access keeps the user's existing access rights.",
    )

    own_contact_access = fields.Boolean(
        string="Own Contact",
        compute="_compute_contact_access",
        inverse="_inverse_own_contact_access",
        groups="base.group_system",
        help="Restrict contacts to this user's salesperson assignment.",
    )
    all_contacts_access = fields.Boolean(
        string="All Contacts (Manager)",
        compute="_compute_contact_access",
        inverse="_inverse_all_contacts_access",
        groups="base.group_system",
        help="Access all contacts within the allowed companies. Overrides Own Contact.",
    )

    @api.depends("groups_id")
    def _compute_contact_access(self):
        own_group = self.env.ref("own_contact.group_own_contact")
        manager_group = self.env.ref("own_contact.group_all_contacts")
        for user in self:
            user.own_contact_access = own_group in user.groups_id
            user.all_contacts_access = manager_group in user.groups_id

    @api.depends("groups_id")
    def _compute_contact_access_mode(self):
        own_group = self.env.ref("own_contact.group_own_contact")
        manager_group = self.env.ref("own_contact.group_all_contacts")
        for user in self:
            user.contact_access_mode = (
                "all" if manager_group in user.groups_id
                else "own" if own_group in user.groups_id
                else "default"
            )

    def _inverse_contact_access_mode(self):
        own_group = self.env.ref("own_contact.group_own_contact")
        manager_group = self.env.ref("own_contact.group_all_contacts")
        for user in self:
            mode = user.contact_access_mode
            user.write({"groups_id": [
                fields.Command.link(own_group.id) if mode == "own"
                else fields.Command.unlink(own_group.id),
                fields.Command.link(manager_group.id) if mode == "all"
                else fields.Command.unlink(manager_group.id),
            ]})

    def _inverse_own_contact_access(self):
        group = self.env.ref("own_contact.group_own_contact")
        for user in self:
            command = fields.Command.link if user.own_contact_access else fields.Command.unlink
            user.write({"groups_id": [command(group.id)]})

    def _inverse_all_contacts_access(self):
        group = self.env.ref("own_contact.group_all_contacts")
        for user in self:
            command = fields.Command.link if user.all_contacts_access else fields.Command.unlink
            user.write({"groups_id": [command(group.id)]})
