# -*- coding: utf-8 -*-
from odoo import api, SUPERUSER_ID


def migrate(cr, version):
    """The Applicable Forms screen used to be free-form create/delete; this
    version replaces it with 4 fixed, xmlid-tracked rows (one per model)
    seeded by data/ziwo_active_form_data.xml. Merge any pre-existing rows
    created via the old UI into the new canonical ones so upgrading doesn't
    leave duplicate rows per model."""
    env = api.Environment(cr, SUPERUSER_ID, {})
    xmlids = [
        'ziwo_active_form_res_partner',
        'ziwo_active_form_crm_lead',
        'ziwo_active_form_sale_order',
        'ziwo_active_form_project_task',
    ]
    for xmlid in xmlids:
        canonical = env.ref('forge_ziwo.%s' % xmlid, raise_if_not_found=False)
        if not canonical:
            continue
        duplicates = env['ziwo.active.form'].with_context(active_test=False).search([
            ('model_id', '=', canonical.model_id.id),
            ('id', '!=', canonical.id),
        ])
        if not duplicates:
            continue
        active_duplicate = duplicates.filtered('active')[:1]
        if active_duplicate:
            canonical.write({
                'active': True,
                'action': active_duplicate.action,
            })
        env['res.company'].sudo().search([
            ('forge_ziwo_active_form_id', 'in', duplicates.ids),
        ]).write({'forge_ziwo_active_form_id': canonical.id})
        duplicates.unlink()
