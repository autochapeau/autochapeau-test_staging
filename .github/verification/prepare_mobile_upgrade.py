"""Add the nullable key before any registry reads newly deployed source."""
import psycopg2
from odoo.tools import config

config.parse_config([])
assert config["db_name"] == "autochapeau_prod_test"
options = {key: config["db_" + key] for key in ("host", "port", "user", "password") if config["db_" + key]}
with psycopg2.connect(dbname=config["db_name"], **options) as connection:
    with connection.cursor() as cursor:
        cursor.execute("ALTER TABLE res_partner ADD COLUMN IF NOT EXISTS mobile_unique_key varchar")
print("MOBILE_UNIQUENESS_SCHEMA=nullable_key_ready")
