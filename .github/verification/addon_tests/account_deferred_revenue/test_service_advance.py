from odoo import Command, fields
from odoo.exceptions import UserError, ValidationError
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install", "service_advance_flow")
class TestServiceAdvance(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.partner = cls.env["res.partner"].create({"name": "QA Deferred Customer"})
        cls.income, cls.liability, cls.tax_account = cls.env["account.account"].create([
            {"name": name, "code": code, "account_type": kind, "company_id": cls.env.company.id}
            for name, code, kind in (("QA Service Revenue", "QADSR", "income"),
                ("QA Service Advances", "QADSL", "liability_current"), ("QA Service Tax", "QADST", "liability_current"))])
        cls.journal = cls.env["account.journal"].create({"name": "QA Deferred Invoice", "code": "QADSI",
            "type": "sale", "default_account_id": cls.income.id, "service_advance_account_id": cls.liability.id,
            "edi_format_ids": [Command.clear()]})
        cls.tax = cls.env["account.tax"].create({"name": "QA Service VAT", "type_tax_use": "sale", "amount": 15,
            "invoice_repartition_line_ids": [Command.create({"repartition_type": "base"}),
                Command.create({"repartition_type": "tax", "account_id": cls.tax_account.id})],
            "refund_repartition_line_ids": [Command.create({"repartition_type": "base"}),
                Command.create({"repartition_type": "tax", "account_id": cls.tax_account.id})]})
        cls.product = cls.env["product.product"].create({"name": "QA Deferred Service", "detailed_type": "service",
            "invoice_policy": "order", "property_account_income_id": cls.income.id, "taxes_id": [Command.set(cls.tax.ids)]})
        brand = cls.env["fleet.vehicle.model.brand"].create({"name": "QA Deferred Brand"})
        model = cls.env["fleet.vehicle.model"].create({"name": "QA Deferred Car", "brand_id": brand.id})
        cls.vehicle = cls.env["fleet.vehicle"].create({"model_id": model.id, "partner_id": cls.partner.id, "vin_sn": "QADEF1234567890"})

    def order(self):
        return self.env["sale.order"].create({"partner_id": self.partner.id, "order_type": "intern",
            "vehicle_id": self.vehicle.id, "state": "sale", "order_line": [Command.create({
                "product_id": self.product.id, "product_uom_qty": 1, "price_unit": 1000, "tax_id": [Command.set(self.tax.ids)]})]})

    def advance(self, order, amount=460):
        wizard = self.env["sale.advance.payment.inv"].create({"sale_order_ids": [Command.set(order.ids)],
            "advance_payment_method": "deferred_service", "fixed_amount": amount,
            "service_advance_journal_id": self.journal.id})
        return wizard._create_invoices(order)

    def post(self, move):
        move.invoice_date = fields.Date.today()
        move.action_post()

    def test_partial_advance_final_invoice_clears_liability_and_tax_once(self):
        order = self.order()
        advance = self.advance(order)
        self.assertAlmostEqual(advance.amount_total, 460)
        self.assertEqual(advance.invoice_line_ids.account_id, self.liability)
        self.post(advance)
        self.assertFalse(advance.commission_entry_ids)
        final = order.with_context(default_journal_id=self.journal.id)._create_invoices(final=True)
        self.assertAlmostEqual(final.amount_total, 690)
        self.post(final)
        all_lines = (advance | final).line_ids
        self.assertAlmostEqual(sum(all_lines.filtered(lambda line: line.account_id == self.liability).mapped("balance")), 0)
        self.assertAlmostEqual(sum(all_lines.filtered(lambda line: line.account_id == self.income).mapped("balance")), -1000)
        self.assertAlmostEqual(sum(all_lines.filtered(lambda line: line.account_id == self.tax_account).mapped("balance")), -150)
        self.assertAlmostEqual(sum(final.commission_entry_ids.mapped("base")), 1000)
        self.assertFalse(advance.deferred_move_ids | final.deferred_move_ids)

    def test_full_advance_final_zero_amount_and_original_account_snapshot(self):
        order = self.order()
        advance = self.advance(order, 1150)
        self.post(advance)
        self.journal.service_advance_account_id = self.tax_account
        final = order.with_context(default_journal_id=self.journal.id)._create_invoices(final=True)
        self.assertAlmostEqual(final.amount_total, 0)
        self.assertEqual(final.invoice_line_ids.filtered("is_service_advance").account_id, self.liability)
        self.post(final)
        self.assertAlmostEqual(sum((advance | final).line_ids.filtered(lambda line: line.account_id == self.liability).mapped("balance")), 0)

    def test_missing_setup_negative_or_excess_advance_rejected(self):
        order = self.order()
        for amount in (0, -1, 1151):
            with self.assertRaises(UserError), self.cr.savepoint():
                self.advance(order, amount)
        self.advance(order, 1000)
        with self.assertRaises(UserError), self.cr.savepoint():
            self.advance(order, 151)
        self.journal.service_advance_account_id = False
        with self.assertRaises(UserError), self.cr.savepoint():
            self.advance(self.order())

    def test_reversal_retains_advance_flag_and_liability(self):
        advance = self.advance(self.order())
        self.post(advance)
        refund = advance._reverse_moves([{"invoice_date": fields.Date.today()}], cancel=False)
        self.post(refund)
        self.assertTrue(refund.invoice_line_ids.is_service_advance)
        self.assertEqual(refund.invoice_line_ids.account_id, self.liability)
        self.assertFalse(refund.commission_entry_ids)

    def test_regular_downpayment_still_uses_regular_income_account(self):
        order = self.order()
        wizard = self.env["sale.advance.payment.inv"].with_context(default_journal_id=self.journal.id).create({
            "sale_order_ids": [Command.set(order.ids)], "advance_payment_method": "fixed", "fixed_amount": 460})
        invoice = wizard._create_invoices(order)
        self.assertFalse(invoice.invoice_line_ids.is_service_advance)
        self.assertNotEqual(invoice.invoice_line_ids.account_id, self.liability)

    def test_invalid_liability_account_rejected(self):
        with self.assertRaises(ValidationError), self.cr.savepoint():
            self.journal.service_advance_account_id = self.income

    def test_tax_included_and_mixed_tax_advances_preserve_order_total(self):
        for included in (False, True):
            self.tax.price_include = included
            order = self.order()
            order.order_line = [Command.create({"product_id": self.product.id, "product_uom_qty": 1,
                "price_unit": 333.33, "tax_id": [Command.clear()]})]
            gross = order.amount_total
            advance = self.advance(order, 444.44)
            self.post(advance)
            final = order.with_context(default_journal_id=self.journal.id)._create_invoices(final=True)
            self.post(final)
            self.assertAlmostEqual(advance.amount_total + final.amount_total, gross)
            self.assertAlmostEqual(sum((advance | final).line_ids.filtered(lambda line: line.account_id == self.liability).mapped("balance")), 0)
            self.assertAlmostEqual(sum((advance | final).mapped("amount_tax")), order.amount_tax)
