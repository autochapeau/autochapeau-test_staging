from odoo.exceptions import AccessError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase, new_test_user


@tagged("post_install", "-at_install")
class TestOwnContact(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.salesperson = new_test_user(
            cls.env, login="own_contact_salesperson", groups="own_contact.group_own_contact"
        )
        cls.other = new_test_user(
            cls.env, login="own_contact_other", groups="own_contact.group_own_contact"
        )
        cls.manager = new_test_user(
            cls.env, login="own_contact_manager",
            groups="own_contact.group_own_contact,own_contact.group_all_contacts",
        )
        cls.unrestricted = new_test_user(
            cls.env, login="own_contact_unrestricted",
            groups="base.group_user,base.group_partner_manager",
        )
        cls.own_partner, cls.other_partner, cls.unassigned = cls.env["res.partner"].sudo().create([
            {"name": "Owned contact", "user_id": cls.salesperson.id},
            {"name": "Another salesperson's contact", "user_id": cls.other.id},
            {"name": "Unassigned contact", "user_id": False},
        ])

    def test_visibility_and_direct_access(self):
        partners = self.own_partner | self.other_partner | self.unassigned
        visible = self.env["res.partner"].with_user(self.salesperson).search([
            ("id", "in", partners.ids),
        ])
        self.assertEqual(visible.ids, self.own_partner.ids)
        for hidden in self.other_partner | self.unassigned:
            with self.assertRaises(AccessError):
                hidden.with_user(self.salesperson).read(["name"])
            with self.assertRaises(AccessError):
                hidden.with_user(self.salesperson).write({"name": "Forbidden"})

    def test_batch_create_forces_current_salesperson(self):
        partners = self.env["res.partner"].with_user(self.salesperson).with_context(
            default_user_id=self.other.id,
        ).create([
            {"name": "New own contact"},
            {"name": "Explicit other owner", "user_id": self.other.id},
            {"name": "Explicit empty owner", "user_id": False},
        ])
        self.assertEqual(partners.mapped("user_id"), self.salesperson)
        defaults = self.env["res.partner"].with_user(self.salesperson).with_context(
            default_user_id=self.other.id,
        ).default_get(["user_id"])
        self.assertEqual(defaults["user_id"], self.salesperson.id)

    def test_cannot_reassign_or_clear_owner(self):
        for owner in (False, self.other.id):
            with self.assertRaises(AccessError):
                self.own_partner.with_user(self.salesperson).write({"user_id": owner})
        self.own_partner.with_user(self.salesperson).write({"name": "Updated own contact"})

    def test_manager_overrides_own_contact_and_can_reassign(self):
        partners = self.own_partner | self.other_partner | self.unassigned
        visible = self.env["res.partner"].with_user(self.manager).search([
            ("id", "in", partners.ids),
        ])
        self.assertEqual(set(visible.ids), set(partners.ids))
        self.other_partner.with_user(self.manager).write({"user_id": self.salesperson.id})
        partner = self.env["res.partner"].with_user(self.manager).create({"name": "Manager contact"})
        self.assertEqual(partner.user_id, self.manager)
        partner = self.env["res.partner"].with_user(self.manager).create({
            "name": "Assigned by manager", "user_id": self.other.id,
        })
        self.assertEqual(partner.user_id, self.other)

    def test_system_partners_are_readable_but_not_editable(self):
        for partner in self.other.partner_id | self.salesperson.company_id.partner_id:
            partner.with_user(self.salesperson).read(["name"])
            with self.assertRaises(AccessError):
                partner.with_user(self.salesperson).write({"comment": "Forbidden"})
        self.salesperson.partner_id.with_user(self.salesperson).write({"phone": "123"})

    def test_user_tab_flags_update_groups_and_cached_rules(self):
        self.assertTrue(self.salesperson.own_contact_access)
        self.assertFalse(self.salesperson.all_contacts_access)
        self.salesperson.write({"all_contacts_access": True})
        self.assertTrue(self.salesperson.has_group("own_contact.group_all_contacts"))
        self.other_partner.with_user(self.salesperson).read(["name"])
        self.salesperson.write({"all_contacts_access": False})
        self.assertFalse(self.salesperson.has_group("own_contact.group_all_contacts"))
        with self.assertRaises(AccessError):
            self.other_partner.with_user(self.salesperson).read(["name"])
        self.salesperson.write({"own_contact_access": False})
        self.assertFalse(self.salesperson.has_group("own_contact.group_own_contact"))

    def test_user_cannot_grant_manager_access(self):
        with self.assertRaises(AccessError):
            self.salesperson.with_user(self.salesperson).write({"all_contacts_access": True})

    def test_unconfigured_users_are_unchanged(self):
        self.other_partner.with_user(self.unrestricted).read(["name"])
        partner = self.env["res.partner"].with_user(self.unrestricted).create({
            "name": "Unrestricted contact", "user_id": False,
        })
        self.assertFalse(partner.user_id)

    def test_broad_group_rule_does_not_bypass_restriction(self):
        self.env["ir.rule"].sudo().create({
            "name": "Test permissive contact rule",
            "model_id": self.env.ref("base.model_res_partner").id,
            "groups": [(4, self.env.ref("own_contact.group_own_contact").id)],
            "domain_force": "[(1, '=', 1)]",
        })
        with self.assertRaises(AccessError):
            self.other_partner.with_user(self.salesperson).read(["name"])

    def test_manager_still_respects_company_boundaries(self):
        company = self.env["res.company"].sudo().create({"name": "Other contact company"})
        partner = self.env["res.partner"].sudo().create({
            "name": "Other company customer", "company_id": company.id,
        })
        with self.assertRaises(AccessError):
            partner.with_user(self.manager).read(["name"])
