"""Recover module upgrades if a previous run pulled source then stopped early."""
import ast
import sys
from pathlib import Path

import psycopg2
from odoo.tools import config

config.parse_config(sys.argv[1:])
database = config["db_name"]
assert database == "autochapeau_prod_test"
options = {key: config["db_" + key] for key in ("host", "port", "user", "password") if config["db_" + key]}
pending = []
with psycopg2.connect(dbname=database, **options) as connection:
    connection.set_session(readonly=True)
    with connection.cursor() as cursor:
        for name in ("partner_management", "workorder_service_components"):
            manifest = ast.literal_eval((Path("/mnt/extra-addons") / name / "__manifest__.py").read_text())
            cursor.execute("SELECT latest_version FROM ir_module_module WHERE name=%s AND state IN ('installed','to upgrade')", [name])
            row = cursor.fetchone()
            if row and row[0] != manifest["version"]:
                pending.append(name)
print(",".join(pending))
