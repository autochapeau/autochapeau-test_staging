import base64

from odoo import Command
from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged

from ..wizard.transfer_proof import check_upload


@tagged("post_install", "-at_install", "payment_attachment")
class TestPaymentAttachment(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.bank = cls.env["account.journal"].create({
            "name": "Attachment Test Bank", "code": "ATBNK", "type": "bank",
        })
        cls.cash = cls.env["account.journal"].create({
            "name": "Attachment Test Cash", "code": "ATCSH", "type": "cash",
        })
        cls.proof = cls.env["ir.attachment"].create({
            "name": "receipt.txt", "datas": base64.b64encode(b"Payment receipt"),
        })

    def test_journal_controls_requirement_for_bank_and_cash(self):
        for journal in self.bank | self.cash:
            check_upload(self.env["ir.attachment"], journal)
            journal.require_payment_attachment = True
            with self.assertRaises(UserError):
                check_upload(self.env["ir.attachment"], journal)
            check_upload(self.proof, journal)
            journal.require_payment_attachment = False
            check_upload(self.env["ir.attachment"], journal)

    def test_wizard_requirement_follows_selected_journal(self):
        self.bank.require_payment_attachment = True
        for model in ("sale.split.payment.wizard", "sale.multi.split.payment.wizard", "account.payment.register"):
            wizard = self.env[model].new({"journal_id": self.bank.id})
            self.assertTrue(wizard.transfer_proof_required)
            wizard.journal_id = self.cash
            self.assertFalse(wizard.transfer_proof_required)
            self.cash.require_payment_attachment = True
            # Reopen after a separate journal configuration change; new()
            # records retain their own onchange cache until the form reloads.
            wizard = self.env[model].new({"journal_id": self.cash.id})
            self.assertTrue(wizard.transfer_proof_required)
            self.cash.require_payment_attachment = False

    def test_collection_requires_upload_before_all_processing_types(self):
        self.bank.require_payment_attachment = True
        for processing_type in ("manual", "terminal", "tabby"):
            method = self.env["sale.collection.method"].create({
                "name": "Attachment " + processing_type,
                "code": "attachment_" + processing_type,
                "processing_type": processing_type, "journal_id": self.bank.id,
            })
            wizard = self.env["sale.split.payment.wizard"].new({
                "collection_method_id": method.id, "journal_id": self.bank.id,
            })
            with self.assertRaisesRegex(UserError, "Upload a payment attachment"):
                wizard.action_collect_payment()

    def test_payment_keeps_owned_attachment_and_checks_requirement(self):
        self.cash.require_payment_attachment = True
        payment = self.env["account.payment"].create({
            "journal_id": self.cash.id, "payment_type": "inbound",
            "partner_type": "customer", "amount": 100,
        })
        with self.assertRaises(UserError):
            payment._check_transfer_proof()
        payment.transfer_proof_ids = [Command.set(self.proof.ids)]
        payment._check_transfer_proof()
        self.assertEqual(payment.transfer_proof_ids.res_model, "account.payment")
        self.assertEqual(payment.transfer_proof_ids.res_id, payment.id)
        self.assertFalse(payment.transfer_proof_ids.public)
        self.cash.require_payment_attachment = False
        payment.transfer_proof_ids = [Command.clear()]
        payment._check_transfer_proof()

    def test_collection_views_have_one_conditionally_required_upload(self):
        from lxml import etree
        for model, view in (
            ("sale.split.payment.wizard", "sale_split_payment.view_sale_split_payment_wizard_form"),
            ("sale.multi.split.payment.wizard", "sale_split_payment.view_sale_multi_split_payment_wizard_form"),
        ):
            arch = etree.fromstring(self.env[model].get_view(self.env.ref(view).id, "form")["arch"])
            self.assertEqual(arch.xpath("//field[@name='journal_id']")[0].get("readonly"), "1")
            uploads = arch.xpath("//field[@name='transfer_proof_ids']")
            self.assertEqual(len(uploads), 1)
            self.assertEqual(uploads[0].get("required"), "transfer_proof_required")
            self.assertIsNone(uploads[0].get("invisible"))


@tagged("post_install", "-at_install", "payment_attachment")
class TestMultiOrderPaymentAttachment(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.partner = cls.env["res.partner"].create({"name": "Multi-order receipt customer"})
        cls.product = cls.env["product.product"].create({
            "name": "Multi-order receipt service", "detailed_type": "service",
            "taxes_id": [Command.clear()],
        })
        cls.journal = cls.env["account.journal"].create({
            "name": "Multi-order receipt bank", "code": "MORCB", "type": "bank",
            "require_payment_attachment": True,
        })
        cls.journal.inbound_payment_method_line_ids.payment_account_id = cls.journal.default_account_id
        cls.method = cls.env["sale.collection.method"].create({
            "name": "Multi-order receipt", "code": "multi_order_receipt_test",
            "processing_type": "manual", "journal_id": cls.journal.id,
        })
        cls.proof = cls.env["ir.attachment"].create({
            "name": "multi-order-receipt.txt", "raw": b"Receipt for both sale orders",
        })
        cls.order_defaults = {}
        if "order_type" in cls.env["sale.order"]._fields:
            cls.order_defaults["order_type"] = "intern"
        if "vehicle_id" in cls.env["sale.order"]._fields:
            brand = cls.env["fleet.vehicle.model.brand"].create({"name": "Receipt test"})
            model = cls.env["fleet.vehicle.model"].create({
                "name": "Receipt test", "brand_id": brand.id,
            })
            vehicle = cls.env["fleet.vehicle"].create({
                "model_id": model.id, "partner_id": cls.partner.id, "vin_sn": "MULTIRECEIPTTEST",
            })
            cls.order_defaults["vehicle_id"] = vehicle.id

    def _wizard(self, amount=15200, proof=True):
        orders = self.env["sale.order"]
        for date, total in (("2026-11-10 19:03:08", 3500), ("2026-11-10 19:08:45", 11700)):
            values = {
                "partner_id": self.partner.id, "state": "sale", "date_order": date,
                "order_line": [Command.create({
                    "product_id": self.product.id, "product_uom_qty": 1,
                    "price_unit": total, "tax_id": [Command.clear()],
                })],
            }
            values.update(self.order_defaults)
            orders |= orders.create(values)
        return self.env["sale.multi.split.payment.wizard"].create({
            "sale_order_ids": [Command.set(orders.ids)],
            "collection_method_id": self.method.id, "journal_id": self.journal.id,
            "amount": amount,
            "transfer_proof_ids": [Command.set(self.proof.ids if proof else [])],
        })

    def _assert_collected(self, wizard, expected_amounts):
        result = wizard.action_collect_payment()
        allocations = wizard.sale_order_ids.split_payment_ids.sorted("sale_order_id")
        payment = allocations.account_payment_id
        self.assertEqual(result["params"]["type"], "success")
        self.assertEqual(allocations.mapped("amount"), expected_amounts)
        self.assertEqual(set(allocations.mapped("state")), {"paid"})
        self.assertEqual(len(payment), 1)
        self.assertEqual(payment.state, "posted")
        self.assertEqual(payment.amount, wizard.amount)
        self.assertEqual(payment.transfer_proof_ids.raw, self.proof.raw)
        self.assertEqual(payment.transfer_proof_ids.res_model, "account.payment")
        self.assertEqual(payment.transfer_proof_ids.res_id, payment.id)
        self.assertFalse(payment.transfer_proof_ids.public)
        for allocation in allocations:
            self.assertEqual(allocation.transfer_proof_ids.raw, self.proof.raw)
            self.assertEqual(allocation.transfer_proof_ids.res_model, "sale.order.payment")
            self.assertEqual(allocation.transfer_proof_ids.res_id, allocation.id)

    def test_full_multi_order_payment_keeps_receipt(self):
        self._assert_collected(self._wizard(), [3500, 11700])

    def test_partial_multi_order_payment_keeps_receipt(self):
        self._assert_collected(self._wizard(amount=4000), [3500, 500])

    def test_multi_order_payment_without_required_receipt_is_rejected(self):
        wizard = self._wizard(proof=False)
        before = self.env["account.payment"].search_count([])
        with self.assertRaisesRegex(UserError, "Upload a payment attachment"):
            wizard.action_collect_payment()
        self.assertFalse(wizard.sale_order_ids.split_payment_ids)
        self.assertEqual(self.env["account.payment"].search_count([]), before)

    def test_multi_order_payment_without_optional_receipt_is_allowed(self):
        self.journal.require_payment_attachment = False
        wizard = self._wizard(proof=False)
        wizard.action_collect_payment()
        allocations = wizard.sale_order_ids.split_payment_ids
        self.assertEqual(set(allocations.mapped("state")), {"paid"})
        self.assertEqual(len(allocations.account_payment_id), 1)
        self.assertEqual(allocations.account_payment_id.state, "posted")
        self.assertFalse(allocations.account_payment_id.transfer_proof_ids)
        self.assertFalse(allocations.transfer_proof_ids)
