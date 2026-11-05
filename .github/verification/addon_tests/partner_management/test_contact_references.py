from odoo.exceptions import AccessError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase, new_test_user


@tagged("post_install", "-at_install", "contact_reference_types")
class TestContactReferenceTypes(TransactionCase):
    def test_each_type_uses_its_own_sequence(self):
        for kind, prefix in (("customer", "CUS"), ("supplier", "VEN"),
                             ("employee", "EMP"), ("agency_salesperson", "AGS")):
            partner = self.env["res.partner"].create({
                "name": "QA " + kind, "contact_partner_type": kind,
            })
            self.assertTrue(partner.ref.startswith(prefix), partner.ref)

    def test_agency_child_gets_reference_but_address_does_not(self):
        parent = self.env["res.partner"].create({"name": "QA agency"})
        agent = self.env["res.partner"].create({
            "name": "QA agency representative", "parent_id": parent.id,
            "contact_partner_type": "agency_salesperson",
        })
        address = self.env["res.partner"].create({
            "name": "QA delivery address", "parent_id": parent.id, "type": "delivery",
        })
        self.assertTrue(agent.ref.startswith("AGS"))
        self.assertFalse(address.ref)

    def test_existing_reference_survives_creation_and_reclassification(self):
        partner = self.env["res.partner"].create({"name": "QA retained code", "ref": "LEGACY-123"})
        partner.contact_partner_type = "employee"
        partner.action_fill_missing_contact_references()
        self.assertEqual(partner.ref, "LEGACY-123")

    def test_backfill_only_selected_missing_references_and_is_idempotent(self):
        first, second = self.env["res.partner"].create([
            {"name": "QA selected employee", "contact_partner_type": "employee"},
            {"name": "QA unselected employee", "contact_partner_type": "employee"},
        ])
        (first | second).write({"ref": False})
        first.action_fill_missing_contact_references()
        reference = first.ref
        self.assertTrue(reference.startswith("EMP"))
        self.assertFalse(second.ref)
        first.action_fill_missing_contact_references()
        self.assertEqual(first.ref, reference)

    def test_existing_imported_reference_is_not_reissued(self):
        sequence = self.env.ref("partner_management.seq_partner_employee")
        sequence.write({"prefix": "QAEMP", "number_next_actual": 1})
        self.env["res.partner"].create({"name": "QA imported", "ref": "QAEMP00001"})
        partner = self.env["res.partner"].create({"name": "QA generated", "contact_partner_type": "employee"})
        self.assertEqual(partner.ref, "QAEMP00002")

    def test_backfill_cannot_be_called_by_ordinary_user(self):
        user = new_test_user(self.env(context=dict(self.env.context, no_reset_password=True)), login="qa_reference_user", groups="base.group_user")
        partner = self.env["res.partner"].create({"name": "QA protected reference"})
        partner.ref = False
        with self.assertRaises(AccessError):
            partner.with_user(user).action_fill_missing_contact_references()
        self.assertFalse(partner.ref)

    def test_employee_and_agency_menus_set_the_matching_default(self):
        from odoo.tools.safe_eval import safe_eval
        for xmlid, kind in (("partner_employee_action", "employee"),
                            ("partner_agency_salesperson_action", "agency_salesperson")):
            action = self.env.ref("partner_management." + xmlid)
            context = safe_eval(action.context)
            self.assertEqual(context["default_contact_partner_type"], kind)
            partner = self.env["res.partner"].with_context(**context).create({"name": "QA menu creation"})
            self.assertEqual(partner.contact_partner_type, kind)
