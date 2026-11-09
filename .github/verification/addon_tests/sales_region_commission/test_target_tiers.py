from unittest.mock import patch

from odoo import Command, fields
from odoo.exceptions import AccessError, ValidationError
from odoo.tests import Form, tagged
from .test_commission import TestCommissionStudio


@tagged("post_install", "-at_install", "target_tiers")
class TestTargetTiers(TestCommissionStudio):
    def _archive_rates(self):
        self.env['sales.commission.rule'].search([]).active = False

    def _shared_rule(self, **values):
        vals = {'name': 'Shared category tiers', 'user_ids': [Command.set((self.alice | self.bob).ids)],
                'date_from': '2026-11-01', 'tier_ids': [Command.create({
                    'kind': 'product', 'category_id': self.category.id,
                    'achievement_from': 0, 'rate': 4})]}
        vals.update(values)
        return self.env['sales.commission.rule'].create(vals)

    def test_shared_rule_uses_each_invoice_salespersons_target(self):
        self._archive_rates()
        rule = self._shared_rule(tier_ids=[Command.create({'kind': 'product', 'category_id': self.category.id,
            'achievement_from': 0, 'achievement_to': 99.99, 'rate': 2}),
            Command.create({'kind': 'product', 'category_id': self.category.id,
            'achievement_from': 100, 'rate': 4})])
        for team, user, amount in ((self.branch, self.alice, 1000), (self.other, self.bob, 2000)):
            self.env['sales.commission.target'].create({'team_id': team.id, 'month': '2026-11-01',
                'amount': amount, 'member_target_ids': [Command.create({'user_id': user.id, 'amount': amount})]})
        with patch.object(fields.Date, 'context_today', return_value=fields.Date.to_date('2026-11-09')):
            self.assertEqual(rule.personal_target, 3000)
            self.assertEqual(rule.with_user(self.alice).personal_target, 1000)
            self.assertEqual(rule.with_user(self.bob).personal_target, 2000)
        for user, target, rate in ((self.alice, 1000, 4), (self.bob, 2000, 2)):
            move = self.invoice(user=user, price=1000)
            move.action_post()
            entry = self.entries(move)
            self.assertEqual(entry.rule_id, rule)
            self.assertEqual(entry.personal_target, target)
            self.assertEqual(entry.rate, rate)
            self.assertEqual(entry.status, 'earned')

    def test_team_default_and_personal_override(self):
        self._archive_rates()
        rule = self._shared_rule(scope='team', team_id=self.branch.id, user_ids=[Command.clear()],
            tier_ids=[Command.clear()], category_id=self.category.id, rate=3)
        move = self.invoice()
        move.action_post()
        self.assertEqual(self.entries(move).rule_id, rule)
        other = self.invoice(user=self.bob)
        other.action_post()
        self.assertEqual(self.entries(other).status, 'review')
        personal = rule.copy({'name': 'Personal exception', 'scope': 'people', 'team_id': False,
                              'user_ids': [Command.set(self.alice.ids)], 'rate': 8})
        move = self.invoice()
        move.action_post()
        self.assertEqual(self.entries(move).rule_id, personal)
        self.assertEqual(self.entries(move).rate, 8)

    def test_product_and_service_tiers_share_achievement_bounds(self):
        self._archive_rates()
        rule = self._shared_rule()
        rule.tier_ids = [Command.create({'kind': 'service', 'service_category_id': self.service_category.id,
            'achievement_from': 0, 'rate': 7})]
        target = self.target()
        target.action_distribute_members()
        for product, rate in ((self.product, 4), (self.service, 7)):
            move = self.invoice(product=product)
            move.action_post()
            self.assertEqual(self.entries(move).rate, rate)
            self.assertEqual(self.entries(move).rule_id, rule)
        with self.assertRaises(ValidationError), self.cr.savepoint():
            rule.tier_ids = [Command.create({'kind': 'service', 'service_category_id': self.service_category.id,
                'achievement_from': 50, 'rate': 9})]

    def test_overlapping_shared_rules_and_direct_tier_edits_rejected(self):
        self._archive_rates()
        rule = self._shared_rule()
        with self.assertRaises(ValidationError), self.cr.savepoint():
            rule.copy({'user_ids': [Command.set(self.bob.ids)]})
        category = self.env['product.category'].create({'name': 'Other shared category'})
        other = rule.copy({'tier_ids': [Command.clear(), Command.create({'kind': 'product',
            'category_id': category.id, 'achievement_from': 0, 'rate': 3})]})
        with self.assertRaises(ValidationError), self.cr.savepoint():
            other.tier_ids.category_id = self.category

    def test_shared_rule_visibility_and_scope_validation(self):
        self._archive_rates()
        rule = self._shared_rule(user_ids=[Command.set(self.alice.ids)])
        self.assertEqual(rule.with_user(self.alice).read(['name'])[0]['name'], rule.name)
        self.assertEqual(rule.tier_ids.with_user(self.alice).read(['rate'])[0]['rate'], 4)
        with self.assertRaises(AccessError):
            rule.with_user(self.bob).read(['name'])
        with self.assertRaises(AccessError):
            rule.tier_ids.with_user(self.bob).read(['rate'])
        with self.assertRaises(ValidationError), self.cr.savepoint():
            rule.user_ids = [Command.clear()]
        with self.assertRaises(ValidationError), self.cr.savepoint():
            rule.write({'scope': 'team', 'team_id': False})
        rule.write({'scope': 'team', 'team_id': self.branch.id, 'user_ids': [Command.clear()]})
        self.assertTrue(rule.with_user(self.alice).read(['name']))
        with self.assertRaises(AccessError):
            rule.with_user(self.bob).read(['name'])

    def test_create_shared_category_tiers_in_form(self):
        self._archive_rates()
        with Form(self.env['sales.commission.rule']) as form:
            form.name = 'Shared tiers from form'
            form.user_ids.add(self.alice)
            form.user_ids.add(self.bob)
            with form.tier_ids.new() as tier:
                tier.kind = 'product'
                tier.category_id = self.category
                tier.achievement_from = 0
                tier.rate = 4
            with form.tier_ids.new() as tier:
                tier.kind = 'service'
                tier.service_category_id = self.service_category
                tier.achievement_from = 0
                tier.rate = 7
        self.assertEqual(len(form.record.tier_ids), 2)
        self.assertEqual(form.record._scope_users(), self.alice | self.bob)

    def test_upgrade_migrates_legacy_selectors_and_preserves_snapshots(self):
        move = self.invoice(price=100)
        move.action_post()
        entry = self.entries(move)
        before = (entry.rule_id.id, entry.rate, entry.amount)
        self.tiers()
        self.env.flush_all()
        self.cr.execute('DELETE FROM sales_commission_rule_user_rel WHERE rule_id=%s', [self.rule.id])
        self.cr.execute('UPDATE sales_commission_rule SET user_id=%s WHERE id=%s', [self.alice.id, self.rule.id])
        self.rule.init()
        self.env['sales.commission.tier'].init()
        self.env.invalidate_all()
        self.assertEqual(self.rule.user_ids, self.alice)
        self.assertFalse(self.rule.user_id)
        self.assertEqual(self.rule.tier_ids.mapped('kind'), ['product', 'product'])
        self.assertEqual(self.rule.tier_ids.category_id, self.category)
        self.assertEqual((entry.rule_id.id, entry.rate, entry.amount), before)
        self.rule.init()
        self.env['sales.commission.tier'].init()
        self.env.invalidate_all()
        self.assertEqual(self.rule.user_ids, self.alice)
        self.assertEqual((entry.rule_id.id, entry.rate, entry.amount), before)

    def test_rule_kind_switch_can_be_saved_from_form(self):
        category = self.env["commission.category"].create({"name": "QA kind switch service"})
        with Form(self.rule) as form:
            form.kind = "service"
            form.service_category_id = category
        self.assertFalse(self.rule.category_id)
        self.assertEqual(self.rule.service_category_id, category)
        with Form(self.rule) as form:
            form.kind = "product"
            form.category_id = self.category
        self.assertFalse(self.rule.service_category_id)
        self.assertEqual(self.rule.category_id, self.category)

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
