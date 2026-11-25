import json

from odoo.exceptions import UserError


assert env.cr.dbname == "autochapeau_prod_test"
assert str(env["ir.config_parameter"].sudo().get_param("database.is_neutralized")).lower() in ("true", "1")
env.cr.execute("SELECT pg_advisory_xact_lock(%s)", (802305123,))
order = env["car.work.order"].sudo().browse(3423).exists()
assert order and order.name == "WO/03416" and order.notes == "DEMO TEST | Workshop Start and Film Unit Validation"
request = order.material_preparation_ids.filtered(lambda row: "Partial Front PPF" in row.service_id.name)
assert len(request) == 1 and request.user_id.name == "Eng Moamed Said"
task = request.task_id
lines = request.line_ids
product = lines.product_id
assert len(product) == 1 and product.default_code == "DEMO-PPF-30"
assert order.state == task.state == "progress" and not task.materials_issued
assert request.state == "prepared" and len(lines) == 3
stock_uom = product.uom_id
used_uom = lines.used_uom_id
assert len(used_uom) == 1 and used_uom.category_id == stock_uom.category_id
assert stock_uom.category_id.name == "DEMO TEST | Roll 30 m"


class RollBackIssue(Exception):
    pass


def verify_finish():
    try:
        with env.cr.savepoint():
            task.with_user(request.user_id).with_company(order.company_id).action_finish()
            assert task.materials_issued and task.state in ("done", "quality")
            raise RollBackIssue()
    except RollBackIssue:
        return True
    except UserError as error:
        assert "Stock could not be reserved completely" in str(error), str(error)
        return False


assert not verify_finish()
stock_uom.rounding = 0.000001
method = "increased demo roll precision"
if not verify_finish():
    location = order._get_branch_warehouse().lot_stock_id
    quants = env["stock.quant"].sudo().with_company(order.company_id)
    roll_balance = quants._get_available_quantity(product, location, allow_negative=True)
    assert roll_balance > 0
    inch_balance = stock_uom._compute_quantity(roll_balance, used_uom)
    quants._update_available_quantity(product, location, -roll_balance)
    product.product_tmpl_id.write({"uom_id": used_uom.id, "uom_po_id": used_uom.id})
    quants._update_available_quantity(product, location, inch_balance)
    stock_uom.rounding = 0.0001
    method = "used inches as the demo film stock unit and converted the demo balance"
    assert verify_finish(), "The demo balance must be reservable after matching the stock and usage units"

assert task.state == "progress" and not task.materials_issued
env.cr.commit()
print("TEST_NEW_PREP_RECORDING_ORDER=" + json.dumps({
    "work_order": order.name, "reserve_precision_issue_verified": True,
    "repair": method, "finish_verified_in_rollback": True,
}), flush=True)
