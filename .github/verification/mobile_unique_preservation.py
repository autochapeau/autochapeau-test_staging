"""Hash existing contact mobile data before/after upgrade; never print mobiles."""
import hashlib
import json
import os
from pathlib import Path

from odoo import tools

phase = os.environ["MOBILE_UPGRADE_PHASE"]
audit_id = os.environ["MOBILE_UPGRADE_AUDIT_ID"]
assert len(audit_id) == 40 and all(c in "0123456789abcdef" for c in audit_id)
directory = Path(tools.config["data_dir"]) / "mobile_unique_upgrade"
directory.mkdir(exist_ok=True)
path = directory / (audit_id + ".json")
env.cr.execute("SELECT id, mobile, mobile_normalized FROM res_partner ORDER BY id")
rows = env.cr.fetchall()
snapshot = {str(row[0]): hashlib.sha256(json.dumps(row, ensure_ascii=False).encode()).hexdigest() for row in rows}
if phase == "before":
    path.write_text(json.dumps(snapshot), encoding="utf-8")
else:
    before = json.loads(path.read_text(encoding="utf-8"))
    assert all(snapshot.get(key) == digest for key, digest in before.items()), "Existing contact mobile data changed"
    env["res.partner"]._ensure_mobile_unique_constraint()
    print("MOBILE_UNIQUENESS_PRESERVATION=" + json.dumps({"database": env.cr.dbname, "existing_contacts_unchanged": len(before)}))
env.cr.rollback()
