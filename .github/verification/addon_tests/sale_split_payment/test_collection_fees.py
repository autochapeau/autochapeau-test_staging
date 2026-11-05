from unittest.mock import patch

from odoo import Command, fields
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged("post_install", "-at_install", "collection_fees_proof")
class TestCollectionFeesProof(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.partner = cls.env["res.partner"].create({"name": "QA Fee Customer"})
        cls.fee_account, cls.tax_account, cls.bank_account, cls.cash_account = cls.env["account.account"].create([
            {"name": name, "code": code, "account_type": kind, "company_id": cls.env.company.id}
            for name, code, kind in (("QA Collection Fee", "QACF", "expense"),
                                     ("QA Fee Tax", "QACFT", "asset_current"),
                                     ("QA Fee Bank", "QACFB", "asset_cash"),
                                     ("QA Fee Cash", "QACFC", "asset_cash"))
        ])
        cls.bank = cls.env["account.journal"].create({
            "name": "QA Collection Bank", "code": "QACB", "type": "bank",
            "default_account_id": cls.bank_account.id, "collection_fee_enabled": True,
            "collection_fee_percent": 1.5, "collection_fee_tax_percent": 15,
            "collection_fee_account_id": cls.fee_account.id, "collection_fee_tax_account_id": cls.tax_account.id,
        })
        cls.cash = cls.env["account.journal"].create({
            "name": "QA Collection Cash", "code": "QACC", "type": "cash", "default_account_id": cls.cash_account.id,
        })
        for journal in cls.bank | cls.cash:
            (journal.inbound_payment_method_line_ids | journal.outbound_payment_method_line_ids).payment_account_id = journal.default_account_id
        cls.method = cls.env["sale.collection.method"].create({
            "name": "QA Bank Transfer", "code": "qa_fee_transfer", "journal_id": cls.bank.id,
            "processing_type": "manual", "company_id": cls.env.company.id,
        })
        brand = cls.env["fleet.vehicle.model.brand"].create({"name": "QA Fee Brand"})
        model = cls.env["fleet.vehicle.model"].create({"name": "QA Fee Car", "brand_id": brand.id})
        cls.vehicle = cls.env["fleet.vehicle"].create({"model_id": model.id, "partner_id": cls.partner.id, "vin_sn": "QAFEE1234567890"})
        cls.product = cls.env["product.product"].create({"name": "QA Fee Service", "detailed_type": "service", "taxes_id": [Command.clear()]})

    def proof(self):
        return self.env["ir.attachment"].create({"name": "QA transfer proof.txt", "raw": b"QA transfer confirmation only", "type": "binary"})

    def payment(self, proof=True, **values):
        journal = values.pop("journal", self.bank)
        defaults = {"payment_type": "inbound", "partner_type": "customer", "partner_id": self.partner.id,
                    "amount": 11500, "journal_id": journal.id, "date": fields.Date.today(),
                    "currency_id": self.env.company.currency_id.id}
        defaults.update(values)
        if proof:
            defaults["transfer_proof_ids"] = [Command.set(self.proof().ids)]
        return self.env["account.payment"].create(defaults)

    def order(self, amount=11500):
        return self.env["sale.order"].create({
            "partner_id": self.partner.id, "order_type": "intern", "vehicle_id": self.vehicle.id,
            "state": "sale", "order_line": [Command.create({"product_id": self.product.id,
                "product_uom_qty": 1, "price_unit": amount, "tax_id": [Command.clear()]})],
        })

    def test_gross_customer_net_bank_fee_tax_and_balanced_entry(self):
        payment = self.payment()
        payment.action_post()
        liquidity, counterpart, extras = payment._seek_for_lines()
        self.assertEqual(payment.amount, 11500)
        self.assertEqual(payment.collection_fee_amount, 172.50)
        self.assertEqual(payment.collection_fee_tax_amount, 25.88)
        self.assertEqual(liquidity.balance, 11301.62)
        self.assertEqual(counterpart.balance, -11500)
        self.assertEqual(extras.filtered(lambda line: line.collection_charge_kind == "fee").account_id, self.fee_account)
        self.assertEqual(extras.filtered(lambda line: line.collection_charge_kind == "tax").account_id, self.tax_account)
        self.assertAlmostEqual(sum(payment.line_ids.mapped("balance")), 0, places=2)
        self.assertEqual(payment.amount_company_currency_signed, 11500)

    def test_draft_amount_edit_recalculates_without_duplicate_fee_lines(self):
        payment = self.payment()
        payment.amount = 10000
        payment.ref = "QA edited"
        self.assertEqual(payment.amount, 10000)
        self.assertEqual(payment.collection_fee_amount, 150)
        self.assertEqual(payment.collection_fee_tax_amount, 22.5)
        self.assertEqual(len(payment.line_ids.filtered("collection_charge_kind")), 2)
        self.assertEqual(payment._seek_for_lines()[0].balance, 9827.5)
        payment.action_post()

    def test_snapshot_keeps_old_rate_after_journal_change(self):
        payment = self.payment()
        payment.action_post()
        balances = payment.line_ids.mapped("balance")
        self.bank.collection_fee_percent = 3
        self.assertEqual(payment.collection_fee_percent, 1.5)
        self.assertEqual(payment.line_ids.mapped("balance"), balances)
        with self.assertRaises(UserError), self.cr.savepoint():
            payment.amount = 12000
        with self.assertRaises(AccessError):
            payment.collection_fee_percent = 0

    def test_reset_and_repost_keep_same_fee_snapshot(self):
        payment = self.payment()
        payment.action_post()
        self.bank.collection_fee_percent = 3
        payment.action_draft()
        payment.action_post()
        self.assertEqual(payment.collection_fee_amount, 172.5)
        self.assertEqual(len(payment.line_ids.filtered("collection_charge_kind")), 2)

    def test_changing_journal_removes_old_fee_lines(self):
        payment = self.payment()
        payment.journal_id = self.cash
        self.assertFalse(payment.collection_fee_account_id)
        self.assertFalse(payment.line_ids.filtered("collection_charge_kind"))
        self.assertEqual(payment._seek_for_lines()[0].amount_currency, 11500)
        payment.action_post()

    def test_outbound_and_supplier_payments_do_not_deduct_receipt_fees(self):
        for overrides in ({"payment_type": "outbound"}, {"partner_type": "supplier"}):
            payment = self.payment(**overrides)
            self.assertFalse(payment.collection_fee_account_id)
            self.assertFalse(payment.line_ids.filtered("collection_charge_kind"))
            payment.action_post()

    def test_foreign_currency_and_forced_balance_remain_balanced(self):
        payment = self.payment(currency_id=self.env.ref("base.USD").id, force_balance=50000)
        payment.action_post()
        liquidity, counterpart, extras = payment._seek_for_lines()
        self.assertEqual(counterpart.balance, -50000)
        self.assertEqual(liquidity.amount_currency, 11301.62)
        self.assertAlmostEqual(sum(payment.line_ids.mapped("balance")), 0, places=2)
        self.assertEqual(payment.amount_company_currency_signed, 50000)

    def test_rounding_small_amount_and_zero_tax(self):
        self.bank.collection_fee_tax_percent = 0
        payment = self.payment(amount=1)
        self.assertEqual(payment.collection_fee_amount, 0.02)
        self.assertEqual(payment.collection_net_amount, 0.98)
        self.assertEqual(len(payment.line_ids.filtered("collection_charge_kind")), 1)
        payment.action_post()

    def test_non_fee_writeoff_is_kept_when_amount_changes(self):
        payment = self.payment(write_off_line_vals=[{"name": "QA Payment Difference", "account_id": self.fee_account.id,
            "partner_id": self.partner.id, "currency_id": self.env.company.currency_id.id, "amount_currency": 10, "balance": 10}])
        payment.amount = 10000
        writeoffs = payment._seek_for_lines()[2]
        other = writeoffs.filtered(lambda line: not line.collection_charge_kind)
        self.assertEqual(other.balance, 10)
        self.assertEqual(payment._seek_for_lines()[1].balance, -10010)
        self.assertAlmostEqual(sum(payment.line_ids.mapped("balance")), 0, places=2)

    def test_invalid_journal_fee_configuration_is_rejected(self):
        for values in ({"collection_fee_percent": -1}, {"collection_fee_percent": 99},
                       {"collection_fee_account_id": self.bank_account.id},
                       {"collection_fee_tax_account_id": self.fee_account.id}):
            with self.assertRaises(ValidationError), self.cr.savepoint():
                self.bank.write(values)

    def test_bank_posting_requires_proof_even_via_move(self):
        payment = self.payment(proof=False)
        with self.assertRaises(UserError), self.cr.savepoint():
            payment.move_id._post(soft=False)
        self.assertEqual(payment.state, "draft")
        payment.transfer_proof_ids = [Command.set(self.proof().ids)]
        payment.action_post()

    def test_cash_does_not_require_transfer_proof(self):
        payment = self.payment(proof=False, journal=self.cash)
        payment.action_post()
        self.assertEqual(payment.state, "posted")

    def test_draft_proof_can_be_removed_and_replaced(self):
        payment = self.payment()
        old = payment.transfer_proof_ids
        old.unlink()
        self.assertFalse(payment.transfer_proof_ids)
        payment.transfer_proof_ids = [Command.set(self.proof().ids)]
        payment.action_post()
        with self.assertRaises(UserError):
            payment.transfer_proof_ids.unlink()
        with self.assertRaises(UserError):
            payment.transfer_proof_ids.write({"raw": b"changed"})
        with self.assertRaises(UserError):
            payment.transfer_proof_ids = [Command.clear()]

    def test_proof_is_copied_to_durable_private_payment_attachment(self):
        original = self.proof()
        payment = self.env["account.payment"].create({"partner_id": self.partner.id, "amount": 100,
            "journal_id": self.bank.id, "payment_type": "inbound", "partner_type": "customer",
            "transfer_proof_ids": [Command.set(original.ids)]})
        self.assertNotEqual(payment.transfer_proof_ids, original)
        self.assertEqual(payment.transfer_proof_ids.res_model, "account.payment")
        self.assertEqual(payment.transfer_proof_ids.res_id, payment.id)
        self.assertFalse(payment.transfer_proof_ids.public)

    def test_url_or_empty_proof_is_rejected(self):
        attachment = self.env["ir.attachment"].create({"name": "QA Link", "type": "url", "url": "https://example.invalid/receipt"})
        payment = self.payment(proof=False)
        with self.assertRaises(ValidationError), self.cr.savepoint():
            payment.transfer_proof_ids = [Command.set(attachment.ids)]

    def test_manual_allocation_requires_proof_before_posting(self):
        allocation = self.env["sale.order.payment"].create({"sale_order_id": self.order().id,
            "collection_method_id": self.method.id, "amount": 11500})
        with self.assertRaises(UserError), self.cr.savepoint():
            allocation.action_process()
        self.assertFalse(allocation.account_payment_id)
        allocation.transfer_proof_ids = [Command.set(self.proof().ids)]
        allocation.action_process()
        self.assertEqual(allocation.state, "paid")
        self.assertEqual(allocation.account_payment_id.amount, 11500)
        self.assertEqual(allocation.account_payment_id.collection_net_amount, 11301.62)

    def test_approved_terminal_retry_never_charges_again(self):
        terminal = self.method.copy({"code": "qa_terminal_confirmed", "processing_type": "terminal"})
        allocation = self.env["sale.order.payment"].create({"sale_order_id": self.order().id,
            "collection_method_id": terminal.id, "amount": 11500})
        with self.assertLogs("odoo.addons.sale_split_payment.models.sale_order_payment", level="ERROR"):
            self.assertFalse(allocation._mark_provider_paid("APPROVED"))
        self.assertEqual(allocation.state, "needs_review")
        self.assertTrue(allocation.provider_payment_confirmed)
        self.assertFalse(allocation.account_payment_id)
        allocation.transfer_proof_ids = [Command.set(self.proof().ids)]
        with patch.object(type(allocation), "_send_card_terminal_payment") as charge:
            allocation.action_process()
            charge.assert_not_called()
        self.assertEqual(allocation.state, "paid")
        self.assertEqual(len(allocation.account_payment_id), 1)

    def test_provider_confirmation_cannot_be_forged_via_write(self):
        allocation = self.env["sale.order.payment"].create({"sale_order_id": self.order().id,
            "collection_method_id": self.method.id, "amount": 100})
        with self.assertRaises(AccessError):
            allocation.provider_payment_confirmed = True

    def test_single_collection_wizard_passes_proof(self):
        wizard = self.env["sale.split.payment.wizard"].create({"sale_order_id": self.order().id,
            "collection_method_id": self.method.id, "journal_id": self.bank.id, "amount": 11500,
            "transfer_proof_ids": [Command.set(self.proof().ids)]})
        wizard.action_collect_payment()
        payment = wizard.sale_order_id.split_payment_ids.account_payment_id
        self.assertEqual(payment.state, "posted")
        self.assertTrue(payment.transfer_proof_ids)

    def test_multiple_orders_share_one_gross_payment_with_proof(self):
        orders = self.order(1000) | self.order(1000)
        wizard = self.env["sale.multi.split.payment.wizard"].create({"sale_order_ids": [Command.set(orders.ids)],
            "collection_method_id": self.method.id, "journal_id": self.bank.id, "amount": 2000,
            "transfer_proof_ids": [Command.set(self.proof().ids)]})
        wizard.action_collect_payment()
        payment = orders.split_payment_ids.account_payment_id
        self.assertEqual(len(payment), 1)
        self.assertEqual(payment.amount, 2000)
        self.assertEqual(payment.collection_net_amount, 1965.5)
        self.assertEqual(sum(orders.split_payment_ids.mapped("amount")), 2000)

    def test_cash_journal_can_apply_configured_collection_fees(self):
        self.cash.write({"collection_fee_enabled": True, "collection_fee_percent": 1.5,
                         "collection_fee_tax_percent": 15, "collection_fee_account_id": self.fee_account.id,
                         "collection_fee_tax_account_id": self.tax_account.id})
        payment = self.payment(proof=False, journal=self.cash)
        payment.action_post()
        self.assertEqual(payment.collection_net_amount, 11301.62)

    def test_posting_checks_fee_lines_after_manual_entry_edit(self):
        payment = self.payment()
        payment.line_ids.filtered(lambda line: line.collection_charge_kind == "fee").with_context(
            skip_account_move_synchronization=True
        ).write({"collection_charge_kind": False})
        with self.assertRaises(ValidationError), self.cr.savepoint():
            payment.move_id._post(soft=False)

    def test_internal_transfer_copies_proof_to_paired_payment_without_fees(self):
        self.env.company.transfer_account_id = self.env["account.account"].create({
            "name": "QA Internal Transfer", "code": "QACIT", "account_type": "asset_current",
            "reconcile": True, "company_id": self.env.company.id,
        })
        payment = self.payment(payment_type="outbound", partner_id=self.env.company.partner_id.id,
                               destination_journal_id=self.cash.id, is_internal_transfer=True)
        payment.action_post()
        paired = payment.paired_internal_transfer_payment_id
        self.assertEqual(paired.state, "posted")
        self.assertTrue(paired.transfer_proof_ids)
        self.assertFalse(payment.collection_fee_account_id | paired.collection_fee_account_id)

    def test_invoice_registration_reconciles_full_customer_amount(self):
        income = self.env["account.account"].search([
            ("company_id", "=", self.env.company.id), ("account_type", "=", "income"), ("deprecated", "=", False)
        ], limit=1)
        journal = self.env["account.journal"].create({"name": "QA Collection Invoice", "code": "QACIN", "type": "sale",
            "edi_format_ids": [Command.clear()], "default_account_id": income.id})
        invoice = self.env["account.move"].create({"move_type": "out_invoice", "partner_id": self.partner.id,
            "journal_id": journal.id, "invoice_date": fields.Date.today(),
            "invoice_line_ids": [Command.create({"name": "QA Collection Invoice", "account_id": income.id,
                "product_id": self.product.id, "quantity": 1, "price_unit": 11500, "tax_ids": [Command.clear()]})]})
        invoice.action_post()
        wizard = self.env["account.payment.register"].with_context(
            active_model="account.move", active_ids=invoice.ids
        ).create({"journal_id": self.bank.id, "payment_date": fields.Date.today(),
                  "transfer_proof_ids": [Command.set(self.proof().ids)]})
        payments = wizard._create_payments()
        self.assertEqual(invoice.amount_residual, 0)
        self.assertEqual(payments.amount, 11500)
        self.assertEqual(payments.collection_net_amount, 11301.62)
        self.assertTrue(payments.transfer_proof_ids)

    def test_empty_bank_payment_register_rejects_before_creation(self):
        wizard = self.env["account.payment.register"].new({"journal_id": self.bank.id})
        with self.assertRaises(UserError):
            wizard._create_payments()

    def test_paid_allocation_requires_matching_posted_ledger(self):
        values = {"sale_order_id": self.order().id, "collection_method_id": self.method.id,
                  "amount": 100, "state": "paid"}
        with self.assertRaises(ValidationError), self.cr.savepoint():
            self.env["sale.order.payment"].create(values)
        payment = self.payment(amount=100)
        with self.assertRaises(ValidationError), self.cr.savepoint():
            self.env["sale.order.payment"].create(dict(values, account_payment_id=payment.id))
        payment.action_post()
        self.env["sale.order.payment"].create(dict(values, account_payment_id=payment.id))
        with self.assertRaises(ValidationError), self.cr.savepoint():
            self.env["sale.order.payment"].create(dict(values, account_payment_id=payment.id))

    def test_context_cannot_forge_provider_confirmation(self):
        allocation = self.env["sale.order.payment"].with_context(default_provider_payment_confirmed=True).create({
            "sale_order_id": self.order().id, "collection_method_id": self.method.id, "amount": 100})
        self.assertFalse(allocation.provider_payment_confirmed)

    def test_reset_retry_reposts_same_payment_and_cancel_updates_allocation(self):
        allocation = self.env["sale.order.payment"].create({"sale_order_id": self.order().id,
            "collection_method_id": self.method.id, "amount": 100,
            "transfer_proof_ids": [Command.set(self.proof().ids)]})
        self.assertTrue(allocation.action_process())
        payment = allocation.account_payment_id
        payment.action_draft()
        self.assertEqual(allocation.state, "needs_review")
        self.assertTrue(allocation.action_process())
        self.assertEqual(allocation.account_payment_id, payment)
        self.assertEqual(payment.state, "posted")
        self.assertEqual(allocation.state, "paid")
        payment.action_draft()
        payment.action_cancel()
        self.assertEqual(allocation.state, "cancelled")

    def test_confirmed_allocation_financial_details_are_immutable(self):
        allocation = self.env["sale.order.payment"].create({"sale_order_id": self.order().id,
            "collection_method_id": self.method.id, "amount": 100,
            "transfer_proof_ids": [Command.set(self.proof().ids)]})
        self.assertTrue(allocation.action_process())
        with self.assertRaises(UserError):
            allocation.amount = 50

    def test_batch_attachment_unlink_cannot_bypass_posted_chatter_proof(self):
        draft = self.payment()
        payment = self.payment(proof=False)
        chatter_proof = self.proof()
        chatter_proof.write({"res_model": "account.payment", "res_id": payment.id})
        payment.action_post()
        with self.assertRaises(UserError):
            (draft.transfer_proof_ids | chatter_proof).unlink()
        self.assertTrue(chatter_proof.exists())
