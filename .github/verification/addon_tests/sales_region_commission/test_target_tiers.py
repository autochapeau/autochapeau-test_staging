from odoo import Command
from odoo.exceptions import AccessError, ValidationError
from odoo.tests import tagged
from .test_commission import TestCommissionStudio


@tagged("post_install", "-at_install", "target_tiers")
class TestTargetTiers(TestCommissionStudio):
    def target(self, amount=1000, period="month", start="2026-11-01"):
        return self.env["sales.commission.target"].create({"team_id": self.branch.id, "month": start,
            "period_type": period, "amount": amount})

    def tiers(self):
        self.rule.tier_ids = [Command.create({"achievement_from": 85, "achievement_to": 99.99, "rate": 2}),
            Command.create({"achievement_from": 100, "achievement_to": 0, "rate": 4})]

    def test_distribution_includes_both_managers_and_rounds_to_total(self):
        self.branch.write({"user_id": self.manager.id, "commission_manager_id": self.admin.id})
        target = self.target(100)
        target.with_user(self.admin).action_distribute_members()
        self.assertEqual(set(target.member_target_ids.user_id.ids), {self.alice.id, self.manager.id, self.admin.id})
        self.assertAlmostEqual(sum(target.member_target_ids.mapped("amount")), 100)
        self.assertEqual(sorted(target.member_target_ids.mapped("amount")), [33.33, 33.33, 33.34])
        with self.assertRaises(AccessError):
            target.with_user(self.alice).action_distribute_members()

    def test_calendar_periods_and_overlap_validation(self):
        for period, start, end in (("quarter", "2026-10-01", "2026-12-31"),
                ("half", "2026-07-01", "2026-12-31"), ("year", "2026-01-01", "2026-12-31")):
            with self.cr.savepoint():
                target = self.target(period=period, start=start)
                self.assertEqual(str(target.date_end), end)
                with self.assertRaises(ValidationError), self.cr.savepoint():
                    self.target()
                target.unlink()
        with self.assertRaises(ValidationError), self.cr.savepoint():
            self.target(period="quarter")

    def test_tier_achievement_and_snapshot_stability(self):
        target = self.target()
        target.action_distribute_members()
        self.tiers()
        move = self.invoice(price=900)
        move.action_post()
        entry = self.entries(move)
        self.assertEqual(entry.achievement_percent, 90)
        self.assertEqual(entry.personal_target, 1000)
        self.assertEqual(entry.rate, 2)
        self.assertEqual(entry.amount, 18)
        second = self.invoice(price=100)
        second.action_post()
        self.assertEqual(self.entries(second).rate, 4)
        self.assertEqual(entry.amount, 18)
        refund = move._reverse_moves([{"invoice_date": "2026-11-03"}])
        refund.action_post()
        self.assertEqual(self.entries(refund).rate, 2)
        self.assertEqual(self.entries(refund).amount, -18)

    def test_discount_adjustment_uses_approved_meaning(self):
        self.rule.apply_discount_adjustment = True
        for discount, expected in ((0, 12), (1, 10), (10, 10), (10.01, 7.5), (20, 7.5)):
            move = self.invoice(price=100, discount=discount)
            move.action_post()
            self.assertAlmostEqual(self.entries(move).rate, expected)
            self.assertAlmostEqual(self.entries(move).amount, move.company_id.currency_id.round(move.amount_untaxed * expected / 100))
        move = self.invoice(discount=30)
        move.action_post()
        self.assertEqual(self.entries(move).status, "review")
        self.assertEqual(self.entries(move).amount, 0)

    def test_missing_or_unbalanced_target_requires_review(self):
        self.tiers()
        move = self.invoice()
        move.action_post()
        self.assertEqual(self.entries(move).status, "review")
        target = self.target()
        target.action_distribute_members()
        target.member_target_ids.amount = 200
        move = self.invoice()
        move.action_post()
        self.assertEqual(self.entries(move).status, "review")

    def test_overlapping_tiers_and_cross_member_share_are_rejected(self):
        self.tiers()
        with self.assertRaises(ValidationError), self.cr.savepoint():
            self.rule.tier_ids = [Command.create({"achievement_from": 99.99, "achievement_to": 101, "rate": 3})]
        target = self.target()
        with self.assertRaises(ValidationError), self.cr.savepoint():
            target.member_target_ids = [Command.create({"user_id": self.bob.id, "amount": 1000})]

    def test_quarterly_dashboard_prorates_and_personal_share_is_private(self):
        target = self.target(3000, "quarter", "2026-10-01")
        self.branch.user_id = self.manager
        target.action_distribute_members()
        monthly = self.env["sales.commission.entry"].with_user(self.alice).dashboard("2026-11-01")
        self.assertEqual(monthly["target"], 500)
        quarter = self.env["sales.commission.entry"].with_user(self.alice).dashboard("2026-11-01", period_type="quarter")
        self.assertEqual(quarter["target"], 1500)
        self.assertEqual(quarter["date_end"], "2026-12-31")
        shares = self.env["sales.commission.target.member"].with_user(self.alice).search([("target_id", "=", target.id)])
        self.assertEqual(shares.user_id, self.alice)

    def test_legacy_settlement_adjustment_sign_and_deferred_exclusion(self):
        employee = self.env["hr.employee"].create({"name": "QA Commission Employee", "user_id": self.alice.id})
        commission = self.env["commission"].create({"name": "QA Legacy Commission",
            "employee_target_ids": [Command.create({"employee_id": employee.id, "target": 10000})],
            "section_ids": [Command.create({"commission_category_id": self.service_category.id,
                "amount_from": 0, "amount_to": 1000, "percent": 10})],
            "discount_section_ids": [Command.create({"amount_from": a, "amount_to": b, "deduction_percent": c})
                for a, b, c in ((0, 0, 20), (1, 10, 0), (10.01, 20, -25))]})
        expected = 0
        for discount, factor in ((0, 1.2), (5, 1), (15, .75)):
            move = self.invoice(product=self.service, price=1000, discount=discount)
            move.invoice_user_id = self.alice
            move.action_post()
            expected += move.amount_untaxed * .1 * factor
        advance = self.invoice(product=self.service, price=1000)
        advance.invoice_user_id = self.alice
        advance.invoice_line_ids.is_service_advance = True
        advance.action_post()
        settlement = self.env["commission.settlement"].create({"commission_ids": [Command.set(commission.ids)],
            "date_from": "2026-11-01", "date_to": "2026-11-30"})
        settlement.generate_commission_lines()
        self.assertAlmostEqual(settlement.total, expected)
        self.assertNotIn(advance.invoice_line_ids, settlement.line_ids.move_line_ids)
