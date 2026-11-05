"""Preserve TEST's manual Saudi QR field in a localization-owned inherited view.

The root account form was manually edited to include a field from l10n_sa.
Cold upgrades of earlier accounting addons validate that root before l10n_sa
loads. Move only that customization; retain all attributes and its position.
Keep a private backup of the original root architecture for reversibility.
"""
import base64
import copy
from lxml import etree

assert env.cr.dbname == "autochapeau_prod_test", "This repair is TEST-only."
root_view = env.ref("account.view_move_form")
tree = etree.fromstring(root_view.arch_db.encode())
nodes = tree.xpath("//field[@name='l10n_sa_qr_code_str']")
if nodes:
    assert "l10n_sa_qr_code_str" in env["account.move"]._fields
    assert len(nodes) == 1, "Review multiple root QR fields manually."
    node = nodes[0]
    previous = node.getprevious()
    parent = node.getparent()
    expression = tree.getroottree().getpath(previous if previous is not None else parent)
    inherited = etree.Element("data")
    insertion = etree.SubElement(inherited, "xpath", expr=expression,
                                 position="after" if previous is not None else "inside")
    insertion.append(copy.deepcopy(node))
    identifier = "l10n_sa.test_preserved_qr_move_form"
    assert not env.ref(identifier, raise_if_not_found=False), "Existing repair requires review."
    env["ir.attachment"].sudo().create({
        "name": "TEST account.view_move_form before QR dependency repair.xml",
        "res_model": "ir.ui.view", "res_id": root_view.id,
        "type": "binary", "mimetype": "application/xml",
        "datas": base64.b64encode(root_view.arch_db.encode()), "public": False,
    })
    view = env["ir.ui.view"].create({
        "name": "TEST preserved Saudi QR field", "model": "account.move",
        "inherit_id": root_view.id, "priority": 15,
        "arch_db": etree.tostring(inherited, encoding="unicode"),
    })
    env["ir.model.data"].create({"module": "l10n_sa", "name": "test_preserved_qr_move_form",
        "model": "ir.ui.view", "res_id": view.id, "noupdate": True})
    parent.remove(node)
    root_view.write({"arch_db": etree.tostring(tree, encoding="unicode")})
    env.cr.commit()
    print("TEST_QR_DEPENDENCY_REPAIR=preserved_in_localization_inherited_view")
else:
    print("TEST_QR_DEPENDENCY_REPAIR=not_needed")
