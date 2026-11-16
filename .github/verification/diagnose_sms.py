"""TEST-only diagnostics. Provider probes have no recipient or message to send."""
import json
from pathlib import Path
from lxml import etree
import requests
from odoo.modules.module import get_module_path

assert env.cr.dbname == "autochapeau_prod_test"
parameters = env["ir.config_parameter"].sudo()
client = parameters.get_param("infinito_client_id", "")
password = parameters.get_param("infinito_client_password", "")
result = {"database": env.cr.dbname, "sms_send_attempted": False,
          "test_otp_bypass_enabled": parameters.get_param("portal_api.allow_test_otp") == "1",
          "credentials": {"client_present": bool(client), "password_present": bool(password),
                          "client_length": len(client), "password_length": len(password),
                          "client_has_surrounding_whitespace": client != client.strip(),
                          "password_has_surrounding_whitespace": password != password.strip()},
          "modules": env["ir.module.module"].search([("name", "in", ["infinito_sms", "sms_test_wizard", "portal_api"])]).read(["name", "state", "latest_version"])}
seed_file = Path(get_module_path("infinito_sms")) / "data/data.xml"
if seed_file.is_file():
    seed = etree.parse(str(seed_file))
    values = {record.findtext('field[@name="key"]'): record.findtext('field[@name="value"]')
              for record in seed.xpath('//record[@model="ir.config_parameter"]')}
    result["credentials"]["match_module_seed"] = (client == values.get("infinito_client_id")
                                                     and password == values.get("infinito_client_password"))
if "sms.test.wizard" in env:
    rows = env["sms.test.wizard"].sudo().search([], order="id desc", limit=10).read(["create_date", "result_status", "last_response"])
    result["previous_wizard_results"] = [{**row, "create_date": str(row["create_date"])} for row in rows]

result["probes"] = []
def probe(name, method, url, **kwargs):
    try:
        response = requests.request(method, url, timeout=20, allow_redirects=False, **kwargs)
        result["probes"].append({"name": name, "status": response.status_code,
            "content_type": response.headers.get("Content-Type"), "body": response.text[:8192]})
    except requests.RequestException as error:
        result["probes"].append({"name": name, "error_type": type(error).__name__})

if client and password:
    # No `to`, `from`, `text` or addresses: these cannot submit an SMS.
    probe("query_auth_without_message", "GET", "https://api.goinfinito.me/unified/v2/send",
          params={"clientid": client, "clientpassword": password})
    probe("header_auth_without_message", "GET", "https://api.goinfinito.me/unified/v2/send",
          headers={"x-client-id": client, "x-client-password": password})
    # The provider's own HTML form documents this read-only balance request.
    credit = etree.Element("REQUESTCREDIT", USERNAME=client, PASSWORD=password)
    probe("account_credit_read_only", "POST", "https://api.goinfinito.me/psms/servlet/psms.Eservice2",
          data={"action": "credits", "data": etree.tostring(credit, encoding="unicode")})
env.cr.rollback()
# Captured into a private runner file and encrypted before any output is shown.
print("SMS_DIAGNOSTIC_PRIVATE=" + json.dumps(result, ensure_ascii=False, default=str))
