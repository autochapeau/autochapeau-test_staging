"""Print only missing required addons, without loading a registry or editing data."""
import os
import sys
import psycopg2
from odoo.tools import config

config.parse_config([])
required = os.environ["VIDEO_VERIFY_REQUIRED_MODULES"].split(",")
database = os.environ["VIDEO_VERIFY_DATABASE"]
options = {key: config["db_" + key] for key in ("host", "port", "user", "password") if config["db_" + key]}
with psycopg2.connect(dbname=database, **options) as connection:
    connection.set_session(readonly=True)
    with connection.cursor() as cursor:
        cursor.execute("SELECT name,state FROM ir_module_module WHERE name=ANY(%s)", [required])
        states = dict(cursor.fetchall())
        cursor.execute("SELECT name,state FROM ir_module_module WHERE name LIKE 'l10n_sa%%' ORDER BY name")
        print("Saudi localization state: " + repr(cursor.fetchall()), file=sys.stderr)
        cursor.execute("SELECT v.id,v.name,v.inherit_id,d.module,d.name FROM ir_ui_view v LEFT JOIN ir_model_data d ON d.model='ir.ui.view' AND d.res_id=v.id WHERE v.active AND v.arch_db::text LIKE %s", ['%l10n_sa_qr_code_str%'])
        print("QR view dependencies: " + repr(cursor.fetchall()), file=sys.stderr)
assert set(states) == set(required), "A required addon is missing from the module catalog."
assert all(state in ("installed", "to upgrade", "uninstalled", "to install") for state in states.values()), states
print(",".join(name for name in required if states[name] in ("uninstalled", "to install")))
