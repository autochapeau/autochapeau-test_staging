from odoo import Command
from odoo.exceptions import AccessError
from odoo.tests import TransactionCase, tagged
from odoo.tools.safe_eval import safe_eval


@tagged("post_install", "-at_install", "partner_contact_edit")
class TestContactEditPermission(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Partner = cls.env["res.partner"].with_context(tracking_disable=True)
        cls.existing = cls.Partner.create({"name": "Existing contact"})
        Users = cls.env["res.users"].with_context(no_reset_password=True)
        cls.creator = Users.create({
            "name": "Contact creator",
            "login": "test_contact_creator",
            "groups_id": [Command.set((
                cls.env.ref("base.group_user") | cls.env.ref("base.group_partner_manager")
            ).ids)],
        })
        cls.reader = Users.create({
            "name": "Contact reader",
            "login": "test_contact_reader",
            "groups_id": [Command.set(cls.env.ref("base.group_user").ids)],
            "can_edit_existing_contacts": True,
        })

    def test_edit_requires_flag_and_existing_access(self):
        contact = self.existing.with_user(self.creator)
        self.assertEqual(contact.name, "Existing contact")
        with self.assertRaisesRegex(AccessError, "Allow editing existing contacts"), self.cr.savepoint():
            contact.write({"email": "blocked@example.test"})
        with self.assertRaises(AccessError), self.cr.savepoint():
            contact.update_address({"street": "Blocked address"})
        with self.assertRaises(AccessError), self.cr.savepoint():
            self.creator.with_user(self.creator).write({"can_edit_existing_contacts": True})
        self.creator.can_edit_existing_contacts = True
        contact.write({"email": "allowed@example.test"})
        self.assertEqual(contact.email, "allowed@example.test")
        with self.assertRaises(AccessError), self.cr.savepoint():
            self.existing.with_user(self.reader).write({"name": "Missing base write access"})
        self.creator.can_edit_existing_contacts = False
        with self.assertRaises(AccessError), self.cr.savepoint():
            contact.write({"name": "Revoked again"})

    def test_creation_keeps_existing_permissions_and_protects_parent(self):
        model = self.Partner.with_user(self.creator)
        contact = model.create({"name": "New contact"})
        self.assertTrue(contact.exists())
        child = model.create({
            "name": "New child address",
            "parent_id": self.existing.id,
            "type": "delivery",
            "street": "New address",
        })
        self.assertEqual(child.street, "New address")
        self.assertFalse(self.existing.street)
        with self.assertRaises(AccessError), self.cr.savepoint():
            child.write({"street": "Change after creation"})
        with self.assertRaises(AccessError), self.cr.savepoint():
            self.Partner.with_user(self.reader).create({"name": "Missing create access"})

    def test_client_form_saves_new_customer_with_mobile_without_edit_permission(self):
        action = self.env.ref("partner_management.partner_customer_action")
        client_form = self.Partner.with_user(self.creator).with_context(**safe_eval(action.context))
        self.assertFalse(self.creator.can_edit_existing_contacts)
        values = {
            "name": "New client from form",
            "country_id": self.env.ref("base.sa").id,
            "mobile": "0599986770",
        }
        [saved] = client_form.web_save(values, {"name": {}, "mobile": {}, "contact_partner_type": {}})
        self.assertEqual(saved["contact_partner_type"], "customer")
        contact = client_form.browse(saved["id"])
        self.assertEqual(contact.sudo().mobile_unique_key, contact._normalize_mobile(values["mobile"]))
        with self.assertRaisesRegex(AccessError, "Allow editing existing contacts"), self.cr.savepoint():
            contact.web_save({"name": "Change to a saved client"}, {"name": {}})

    def test_contract_form_allows_unchanged_owner_details_but_blocks_changes(self):
        self.creator.groups_id = [Command.link(self.env.ref("sales_team.group_sale_salesman").id)]
        owner = self.Partner.create({"name": "Contract vehicle owner", "partner_type": "internal",
                                    "email": "owner@example.test"})
        customer = self.Partner.create({"name": "Contract customer", "partner_type": "contract"})
        orders = self.env["sale.order"].with_user(self.creator).with_context(
            default_subordinate_id=owner.id, tracking_disable=True,
        )
        values = {"order_type": "contract", "partner_id": customer.id, "subordinate_email": owner.email}
        [saved] = orders.web_save(values, {"name": {}})
        order = orders.browse(saved["id"])
        self.assertEqual(order.subordinate_id, owner)
        order.web_save({"subordinate_email": owner.email, "client_order_ref": "Reference"}, {"name": {}})
        self.assertEqual(order.client_order_ref, "Reference")
        with self.assertRaisesRegex(AccessError, "Allow editing existing contacts"), self.cr.savepoint():
            order.web_save({"subordinate_email": "changed@example.test"}, {"name": {}})
        self.assertEqual(owner.email, "owner@example.test")
