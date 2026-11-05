from odoo import Command, fields
from odoo.exceptions import AccessError, ValidationError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase, new_test_user


@tagged("post_install", "-at_install", "team_analytic_sales")
class TestTeamAnalytic(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.plan = cls.env["account.analytic.plan"].create({"name": "QA Sales Regions"})
        cls.other_plan = cls.env["account.analytic.plan"].create({"name": "QA Other Allocation"})
        cls.region, cls.manual, cls.next_region = cls.env["account.analytic.account"].create([
            {"name": name, "plan_id": cls.plan.id, "company_id": cls.env.company.id}
            for name in ("QA North", "QA Manual", "QA South")
        ])
        cls.other_account = cls.env["account.analytic.account"].create({
            "name": "QA Project", "plan_id": cls.other_plan.id, "company_id": cls.env.company.id,
        })
        cls.team = cls.env["crm.team"].create({"name": "QA North Team", "company_id": cls.env.company.id,
                                              "sales_analytic_account_id": cls.region.id})
        cls.next_team = cls.env["crm.team"].create({"name": "QA South Team", "company_id": cls.env.company.id,
                                                   "sales_analytic_account_id": cls.next_region.id})
        cls.partner = cls.env["res.partner"].create({"name": "QA Analytics Customer"})
        brand = cls.env["fleet.vehicle.model.brand"].create({"name": "QA Analytics"})
        model = cls.env["fleet.vehicle.model"].create({"name": "QA Analytics", "brand_id": brand.id})
        cls.vehicle = cls.env["fleet.vehicle"].create({
            "model_id": model.id, "partner_id": cls.partner.id, "vin_sn": "QAANALYTIC1234567",
        })
        cls.product = cls.env["product.product"].create({"name": "QA Analytics Service", "detailed_type": "service"})

    def order(self, distribution=None):
        line = {"product_id": self.product.id, "product_uom_qty": 1, "price_unit": 100}
        if distribution is not None:
            line["analytic_distribution"] = distribution
        return self.env["sale.order"].create({"partner_id": self.partner.id, "team_id": self.team.id,
                                              "order_type": "intern", "vehicle_id": self.vehicle.id,
                                              "order_line": [Command.create(line)]})

    def test_default_reaches_order_and_invoice_values(self):
        order = self.order()
        self.assertEqual(order.order_line.analytic_distribution[str(self.region.id)], 100)
        values = order.order_line._prepare_invoice_line(quantity=1)
        self.assertEqual(values["analytic_distribution"][str(self.region.id)], 100)
        move = self.env["account.move"].create({"partner_id": self.partner.id, "move_type": "out_invoice",
                                                "invoice_line_ids": [Command.create(values)]})
        self.assertEqual(move.invoice_line_ids.analytic_distribution[str(self.region.id)], 100)

    def test_other_plans_and_manual_same_plan_allocations_are_preserved(self):
        original = {str(self.other_account.id): 100}
        merged, applied = self.team._merge_team_analytic_distribution(original, self.env.company)
        self.assertTrue(applied)
        self.assertEqual(merged, {str(self.other_account.id): 100, str(self.region.id): 100})
        original[str(self.manual.id)] = 100
        merged, applied = self.team._merge_team_analytic_distribution(original, self.env.company)
        self.assertFalse(applied)
        self.assertEqual(merged, original)

    def test_team_change_replaces_only_untouched_generated_default(self):
        order = self.order()
        distribution = dict(order.order_line.analytic_distribution)
        distribution[str(self.other_account.id)] = 100
        order.order_line.analytic_distribution = distribution
        order.team_id = self.next_team
        self.assertNotIn(str(self.region.id), order.order_line.analytic_distribution or {})
        self.assertEqual(order.order_line.analytic_distribution[str(self.next_region.id)], 100)
        self.assertEqual(order.order_line.analytic_distribution[str(self.other_account.id)], 100)

    def test_removing_team_clears_only_generated_allocation(self):
        order = self.order()
        order.team_id = False
        self.assertNotIn(str(self.region.id), order.order_line.analytic_distribution or {})

    def test_backfill_previews_protects_existing_and_is_idempotent(self):
        order = self.order({str(self.other_account.id): 100})
        action = order.action_prepare_team_analytic_backfill()
        wizard = self.env["team.analytic.backfill"].browse(action["res_id"])
        self.assertEqual(wizard.eligible_count, 1)
        self.assertEqual(order.order_line.analytic_distribution, {str(self.other_account.id): 100})
        wizard.action_apply()
        distribution = order.order_line.analytic_distribution
        self.assertEqual(distribution[str(self.region.id)], 100)
        self.assertEqual(distribution[str(self.other_account.id)], 100)
        wizard.action_apply()
        self.assertEqual(order.order_line.analytic_distribution, distribution)
        order.order_line.analytic_distribution = {str(self.manual.id): 100}
        self.assertEqual(len(wizard._planned_updates()[0]), 0)

    def test_subplans_are_treated_as_one_plan(self):
        child = self.env["account.analytic.plan"].create({"name": "QA Subregion", "parent_id": self.plan.id})
        account = self.env["account.analytic.account"].create({"name": "QA Subregion Account", "plan_id": child.id})
        merged, applied = self.team._merge_team_analytic_distribution({str(account.id): 100}, self.env.company)
        self.assertFalse(applied)
        self.assertEqual(merged, {str(account.id): 100})

    def test_cross_company_and_archived_configuration_is_rejected(self):
        self.region.active = False
        with self.assertRaises(ValidationError):
            self.team._merge_team_analytic_distribution({}, self.env.company)
        self.region.active = True
        # A supplied order company must match the configured account's company.
        with self.assertRaises(ValidationError):
            self.team._merge_team_analytic_distribution({}, self.env["res.company"])

    def test_historical_update_requires_manager_even_via_direct_rpc(self):
        user = new_test_user(self.env(context=dict(self.env.context, no_reset_password=True)),
                             login="qa_analytic_user", groups="base.group_user,sales_team.group_sale_salesman")
        order = self.order()
        with self.assertRaises(AccessError):
            order.with_user(user).action_prepare_team_analytic_backfill()

    def test_posted_invoice_backfill_creates_analytics_without_financial_changes(self):
        order = self.order()
        journal = self.env["account.journal"].create({
            "name": "QA Analytic Invoice", "code": "QAAN", "type": "sale",
            "edi_format_ids": [Command.clear()],
            "company_id": self.env.company.id,
            "default_account_id": self.env["account.account"].search([
                ("company_id", "=", self.env.company.id), ("account_type", "=", "income"),
                ("deprecated", "=", False),
            ], limit=1).id,
        })
        values = order.order_line._prepare_invoice_line(quantity=1)
        values["analytic_distribution"] = False
        move = self.env["account.move"].create({
            "partner_id": self.partner.id, "move_type": "out_invoice", "journal_id": journal.id,
            "invoice_date": fields.Date.today(), "invoice_line_ids": [Command.create(values)],
        })
        move.action_post()
        before = (move.name, move.state, move.amount_total, move.amount_tax, move.amount_residual,
                  [(line.id, line.balance, line.account_id.id) for line in move.line_ids])
        action = move.action_prepare_team_analytic_backfill()
        wizard = self.env["team.analytic.backfill"].browse(action["res_id"])
        self.assertEqual(wizard.eligible_count, 1)
        wizard.action_apply()
        self.assertEqual(move.invoice_line_ids.analytic_distribution[str(self.region.id)], 100)
        self.assertTrue(move.invoice_line_ids.analytic_line_ids)
        self.assertEqual(before, (move.name, move.state, move.amount_total, move.amount_tax, move.amount_residual,
                                 [(line.id, line.balance, line.account_id.id) for line in move.line_ids]))

    def test_combined_keys_keep_allocation_in_other_plan_when_team_changes(self):
        merged, generated = self.next_team._merge_team_analytic_distribution(
            {str(self.region.id) + "," + str(self.other_account.id): 100},
            self.env.company, previous_auto=self.region,
        )
        self.assertTrue(generated)
        self.assertEqual(merged, {str(self.other_account.id): 100, str(self.next_region.id): 100})
