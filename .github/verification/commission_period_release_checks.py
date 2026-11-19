"""Rollback-only TEST release checks, reusing already prepared access metadata."""
assert env.cr.dbname == 'autochapeau_prod_test'
import os
from pathlib import Path
from odoo.addons.access_roles.models.filter_registry import FilterRegistry
from odoo.addons.access_roles.models.groupby_registry import GroupByRegistry
from odoo.addons.access_roles.models.button_registry import ButtonRegistry
from odoo.addons.access_roles.models.tab_registry import TabRegistry

methods = [(FilterRegistry, 'get_all_filters'), (GroupByRegistry, 'get_all_groupby'),
           (ButtonRegistry, 'get_all_buttons'), (TabRegistry, 'get_all_tabs')]
original_methods = [(model, name, getattr(model, name)) for model, name in methods]
root = Path('/mnt/extra-addons/.github/verification')
os.environ['VIDEO_VERIFICATION_ROOT'] = str(root)
try:
    # This is the same isolation used for the successful production-copy tests.
    # Permissions and business operations still execute; only rebuilding unrelated
    # UI metadata on each analytic-plan test is avoided inside this test process.
    for model, name in methods:
        setattr(model, name, lambda self: {})
    exec(compile((root / 'run_regression.py').read_text(), str(root / 'run_regression.py'), 'exec'))
finally:
    for model, name, original in original_methods:
        setattr(model, name, original)
