from odoo import api, SUPERUSER_ID


def migrate(cr, version):
    # Restore the normal application selectors even if a previous deployment
    # left base.user_groups_view with its temporary upgrade architecture.
    env = api.Environment(cr, SUPERUSER_ID, {})
    env['res.groups']._update_user_groups_view()
