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
    inherited = etree.Element("data")
    placements = []
    for node in nodes:
        previous, following = node.getprevious(), node.getnext()
        while previous is not None and previous in nodes:
            previous = previous.getprevious()
        while following is not None and following in nodes:
            following = following.getnext()
        anchor = previous if previous is not None else following
        placements.append((node, anchor if anchor is not None else node.getparent(),
                           "after" if previous is not None else "before" if following is not None else "inside"))
    for node in nodes:
        node.getparent().remove(node)
    insertions = {}
    for node, anchor, position in placements:
        key = (anchor, position)
        if key not in insertions:
            insertions[key] = etree.SubElement(inherited, "xpath",
                expr=tree.getroottree().getpath(anchor), position=position)
        insertions[key].append(copy.deepcopy(node))
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
    root_view.write({"arch_db": etree.tostring(tree, encoding="unicode")})
    env.cr.commit()
    print("TEST_QR_DEPENDENCY_REPAIR=preserved_in_localization_inherited_view nodes=%d" % len(nodes))
else:
    print("TEST_QR_DEPENDENCY_REPAIR=not_needed")
