import unittest

from psycopg2 import IntegrityError

from odoo.exceptions import ValidationError
from odoo.tests import TransactionCase, tagged
from odoo.tools import mute_logger


@tagged("post_install", "-at_install", "partner_mobile_unique")
class TestMobileUnique(TransactionCase):
    def setUp(self):
        super().setUp()
        self.Partner = self.env["res.partner"].with_context(tracking_disable=True)
        self.values = {"name": "Mobile uniqueness test", "country_id": self.env.ref("base.sa").id}

    def create_partner(self, **values):
        return self.Partner.create(dict(self.values, **values))

    def assert_duplicate(self, operation):
        # SQL violations are translated to ValidationError by the RPC layer.
        with unittest.TestCase.assertRaises(self, (ValidationError, IntegrityError)), self.cr.savepoint(), mute_logger("odoo.sql_db"):
            operation()

    def test_create_and_equivalent_formats(self):
        self.create_partner(mobile="0599986733")
        for mobile in ("0599986733", "+966 59 998 6733", "00966599986733", "599986733"):
            with self.subTest(mobile=mobile):
                self.assert_duplicate(lambda: self.create_partner(mobile=mobile))

    def test_write_and_same_contact(self):
        partner = self.create_partner(mobile="0599986734")
        other = self.create_partner(mobile="0599986735")
        partner.write({"mobile": "+966 59 998 6734"})
        self.assert_duplicate(lambda: other.write({"mobile": "00966599986734"}))

    def test_archived_contact(self):
        self.create_partner(mobile="0599986736", active=False)
        self.assert_duplicate(lambda: self.create_partner(mobile="+966599986736"))

    def test_batch_create(self):
        self.assert_duplicate(lambda: self.Partner.create([
            dict(self.values, mobile="0599986737"),
            dict(self.values, mobile="+966599986737"),
        ]))

    def test_empty_mobile_and_shared_phone(self):
        partners = self.Partner.create([
            dict(self.values, mobile=False, phone="0599986738"),
            dict(self.values, mobile=False, phone="0599986738"),
        ])
        self.assertEqual(len(partners), 2)

    def test_clear_and_reuse_mobile(self):
        partner = self.create_partner(mobile="0599986739")
        partner.mobile = False
        self.create_partner(mobile="+966599986739")

    def test_database_constraint(self):
        first = self.create_partner(mobile="0599986740")
        second = self.create_partner(mobile="0599986741")
        self.env.flush_all()
        # Direct SQL bypasses ORM checks, as a simultaneous transaction could.
        with self.assertRaises(IntegrityError), self.cr.savepoint(), mute_logger("odoo.sql_db"):
            self.cr.execute(
                "UPDATE res_partner SET mobile_unique_key = %s WHERE id = %s",
                [first.mobile_unique_key, second.id],
            )

    def test_legacy_duplicates_preserved(self):
        first = self.create_partner(mobile="0599986742")
        second = self.create_partner(mobile="0599986743")
        self.env.flush_all()
        # Reproduce rows present before installing the new key column.
        self.cr.execute(
            "UPDATE res_partner SET mobile = %s, mobile_normalized = %s, mobile_unique_key = NULL WHERE id IN %s",
            ["0599986742", "+966599986742", tuple((first | second).ids)],
        )
        (first | second).invalidate_recordset(["mobile", "mobile_normalized", "mobile_unique_key"])
        first.write({"name": "Legacy contact retained", "mobile": "+966 59 998 6742"})
        self.assertEqual(second.mobile, "0599986742")
        self.assert_duplicate(lambda: self.create_partner(mobile="+966599986742"))
        third = self.create_partner(mobile="0599986744")
        self.assert_duplicate(lambda: third.write({"mobile": "+966599986742"}))
        second.write({"mobile": "0599986745"})
        self.assert_duplicate(lambda: second.write({"mobile": "+966599986742"}))

    def test_defaults_and_key_cannot_disable_validation(self):
        first = self.create_partner(mobile="0599986746")
        self.assert_duplicate(lambda: self.Partner.with_context(default_mobile=first.mobile).create(self.values))
        self.assert_duplicate(lambda: self.create_partner(mobile=first.mobile, mobile_unique_key=False))
        other = self.create_partner(mobile="0599986747")
        self.assert_duplicate(lambda: other.write({"mobile": first.mobile, "mobile_unique_key": False}))
