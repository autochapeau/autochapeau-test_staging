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
