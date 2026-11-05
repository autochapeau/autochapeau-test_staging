from odoo import Command
from odoo.exceptions import AccessError, UserError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase, new_test_user


@tagged("post_install", "-at_install", "cash_custody_flow")
class TestCashCustody(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        context = cls.env(context=dict(cls.env.context, no_reset_password=True))
        cls.collector, cls.coach, cls.manager, cls.stranger = [
            new_test_user(context, login="qa_cash_" + role,
                          groups="base.group_user,sale_split_payment.group_split_payment_cashier")
            for role in ("collector", "coach", "manager", "stranger")
        ]
        cls.collector_employee, cls.coach_employee, cls.manager_employee = cls.env["hr.employee"].create([
            {"name": "QA Cash " + role, "user_id": user.id, "company_id": cls.env.company.id}
            for role, user in (("Collector", cls.collector), ("Coach", cls.coach), ("Manager", cls.manager))
        ])
        cls.collector_employee.write({"coach_id": cls.coach_employee.id, "parent_id": cls.manager_employee.id})
        account = cls.env["account.account"].create({"name": "QA Custody Cash", "code": "QACUS",
            "account_type": "asset_cash", "company_id": cls.env.company.id})
        cls.journal = cls.env["account.journal"].create({"name": "QA Custody Cash", "code": "QACU", "type": "cash",
                                                        "default_account_id": account.id})
        cls.journal.inbound_payment_method_line_ids.payment_account_id = account
        cls.method = cls.env["sale.collection.method"].create({"name": "QA Custody Cash", "code": "qa_cash_custody",
            "journal_id": cls.journal.id, "processing_type": "manual", "company_id": cls.env.company.id})
        cls.partner = cls.env["res.partner"].create({"name": "QA Cash Customer"})
        brand = cls.env["fleet.vehicle.model.brand"].create({"name": "QA Custody"})
        model = cls.env["fleet.vehicle.model"].create({"name": "QA Custody", "brand_id": brand.id})
        cls.vehicle = cls.env["fleet.vehicle"].create({"model_id": model.id, "partner_id": cls.partner.id,
                                                     "vin_sn": "QACUSTODY1234567"})
        cls.product = cls.env["product.product"].create({"name": "QA Cash Service", "detailed_type": "service", "taxes_id": [Command.clear()]})

    def order(self):
        return self.env["sale.order"].create({"partner_id": self.partner.id, "order_type": "intern",
            "vehicle_id": self.vehicle.id, "state": "sale", "user_id": self.collector.id,
            "order_line": [Command.create({"product_id": self.product.id, "product_uom_qty": 1,
                "price_unit": 100, "tax_id": [Command.clear()]})]})

    def receipt(self):
        payment = self.env["account.payment"].create({"journal_id": self.journal.id, "amount": 100,
            "partner_id": self.partner.id, "payment_type": "inbound", "partner_type": "customer",
            "cash_collector_user_id": self.collector.id})
        payment.action_post()
        allocation = self.env["sale.order.payment"].create({"sale_order_id": self.order().id,
            "collection_method_id": self.method.id, "amount": 100, "state": "paid", "account_payment_id": payment.id})
        return payment, allocation

    def test_full_hierarchy_via_cashier_actions_keeps_one_accounting_entry(self):
        payment, allocation = self.receipt()
        before = (payment.move_id.id, payment.move_id.line_ids.ids, payment.move_id.line_ids.mapped("balance"))
        self.assertEqual(payment.cash_holder_user_id, self.collector)
        self.assertEqual(payment.cash_stage, "collected")
        allocation.with_user(self.collector).action_send_cash_to_coach()
        self.assertEqual(payment.cash_holder_employee_id, self.coach_employee)
        self.assertEqual(allocation.cash_holder_name, self.coach_employee.name)
        allocation.with_user(self.coach).action_send_cash_to_manager()
        self.assertEqual(payment.cash_holder_user_id, self.manager)
        self.assertEqual(payment.cash_stage, "manager")
        self.assertEqual(len(payment.cash_transfer_ids), 3)
        self.assertEqual(set(payment.cash_transfer_ids.mapped("actor_id").ids), {self.collector.id, self.coach.id})
        self.assertEqual(before, (payment.move_id.id, payment.move_id.line_ids.ids, payment.move_id.line_ids.mapped("balance")))

    def test_previous_holder_and_unrelated_user_cannot_move_cash(self):
        payment, allocation = self.receipt()
        with self.assertRaises(AccessError):
            allocation.with_user(self.stranger).action_send_cash_to_coach()
        allocation.with_user(self.collector).action_send_cash_to_coach()
        with self.assertRaises(AccessError):
            allocation.with_user(self.collector).action_send_cash_to_manager()
        self.assertEqual(payment.cash_stage, "coach")

    def test_manager_route_cannot_skip_configured_coach(self):
        payment, allocation = self.receipt()
        with self.assertRaises(UserError):
            allocation.with_user(self.collector).action_send_cash_to_manager()
        self.assertEqual(len(payment.cash_transfer_ids), 1)

    def test_return_before_reset_then_repost_has_clear_history(self):
        payment, allocation = self.receipt()
        allocation.with_user(self.collector).action_send_cash_to_coach()
        with self.assertRaises(UserError):
            payment.action_draft()
        self.assertEqual(payment.state, "posted")
        allocation.with_user(self.coach).action_return_cash_to_collector()
        self.assertEqual(payment.cash_holder_user_id, self.collector)
        payment.action_draft()
        self.assertFalse(payment.cash_stage)
        payment.action_post()
        self.assertEqual(payment.cash_stage, "collected")
        self.assertEqual(len(payment.cash_transfer_ids), 4)

    def test_history_and_holder_fields_cannot_be_forged(self):
        payment, allocation = self.receipt()
        with self.assertRaises(AccessError):
            payment.cash_holder_user_id = self.stranger
        with self.assertRaises(AccessError):
            payment.cash_transfer_ids.write({"to_name": "Forged"})
        with self.assertRaises(AccessError):
            payment.cash_transfer_ids.unlink()
        with self.assertRaises(AccessError):
            self.env["cash.custody.transfer"].with_user(self.collector).create({
                "payment_id": payment.id, "company_id": payment.company_id.id, "currency_id": payment.currency_id.id,
                "amount": 100, "actor_id": self.collector.id, "to_name": "Forged", "stage": "manager"})

    def test_missing_coach_can_route_directly_to_configured_manager(self):
        self.collector_employee.coach_id = False
        payment, allocation = self.receipt()
        with self.assertRaises(UserError):
            allocation.with_user(self.collector).action_send_cash_to_coach()
        allocation.with_user(self.collector).action_send_cash_to_manager()
        self.assertEqual(payment.cash_holder_employee_id, self.manager_employee)

    def test_duplicate_post_initialization_does_not_duplicate_history(self):
        payment, allocation = self.receipt()
        payment._initialize_cash_custody()
        self.assertEqual(len(payment.cash_transfer_ids), 1)

    def test_actual_cashier_collection_records_actor_across_sudo_boundary(self):
        allocation = self.env["sale.order.payment"].with_user(self.collector).create({
            "sale_order_id": self.order().id, "collection_method_id": self.method.id, "amount": 100,
        })
        allocation.with_user(self.collector).action_process()
        self.assertEqual(allocation.state, "paid")
        self.assertEqual(allocation.account_payment_id.cash_collector_user_id, self.collector)
        self.assertEqual(allocation.account_payment_id.cash_holder_employee_id, self.collector_employee)
        allocation.with_user(self.collector).action_send_cash_to_coach()
        self.assertEqual(allocation.account_payment_id.cash_holder_user_id, self.coach)
