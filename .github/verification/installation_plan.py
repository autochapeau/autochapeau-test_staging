"""Print only missing required addons, without loading a registry or editing data."""
import os
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
assert set(states) == set(required), "A required addon is missing from the module catalog."
assert all(state in ("installed", "to upgrade", "uninstalled", "to install") for state in states.values()), states
print(",".join(name for name in required if states[name] in ("uninstalled", "to install")))
