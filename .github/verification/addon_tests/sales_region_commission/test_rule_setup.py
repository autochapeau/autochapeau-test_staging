from psycopg2 import IntegrityError
from odoo import Command, fields
from odoo.exceptions import ValidationError
from odoo.tests import Form, tagged
from .test_commission import TestCommissionStudio


@tagged('post_install', '-at_install', 'commission_setup_notes')
class TestCommissionSetupNotes(TestCommissionStudio):
    def test_target_duplicate_skips_occupied_period_and_copies_shares_notes(self):
        target = self.env['sales.commission.target'].create({'team_id': self.branch.id,
            'month': '2026-11-01', 'amount': 1000, 'notes': 'Agreed allocation',
            'member_target_ids': [Command.create({'user_id': self.alice.id, 'amount': 1000})]})
        self.env['sales.commission.target'].create({'team_id': self.branch.id,
            'month': '2026-12-01', 'amount': 1000})
        duplicate = target.copy()
        self.assertEqual(str(duplicate.month), '2027-01-01')
        self.assertEqual(duplicate.notes, target.notes)
        self.assertEqual(duplicate.amount, target.amount)
        self.assertEqual(duplicate.member_target_ids.user_id, self.alice)
        self.assertEqual(duplicate.member_target_ids.amount, 1000)
        self.assertNotEqual(duplicate.member_target_ids, target.member_target_ids)
        duplicate.notes = 'New agreement'
        self.assertEqual(target.notes, 'Agreed allocation')
        with self.assertRaises(IntegrityError), self.cr.savepoint():
            target.copy({'month': target.month})

    def test_duplicate_calendar_periods_and_year_boundary(self):
        for period, start, expected in [('quarter', '2026-10-01', '2027-01-01'),
                ('half', '2026-07-01', '2027-01-01'), ('year', '2026-01-01', '2027-01-01')]:
            with self.cr.savepoint():
                target = self.env['sales.commission.target'].create({'team_id': self.branch.id,
                    'month': start, 'period_type': period, 'amount': 1000})
                duplicate = target.copy()
                self.assertEqual(str(duplicate.month), expected)
                (target | duplicate).unlink()

    def test_new_form_explicit_method_and_empty_tiers_validation(self):
        self.rule.active = False
        Rule = self.env['sales.commission.rule']
        form = Form(Rule)
        self.assertEqual(form.calculation_method, 'tiers')
        form.name = 'Explicit tier rule'
        form.user_ids.add(self.alice)
        form.date_from = fields.Date.to_date('2026-11-01')
        with form.tier_ids.new() as tier:
            tier.kind = 'product'
            tier.category_id = self.category
            tier.achievement_from = 0
            tier.rate = 4
        rule = form.save()
        self.assertEqual(rule.calculation_method, 'tiers')
        self.assertEqual(rule.tier_ids.rate, 4)
        before = rule.tier_ids.read(['kind', 'category_id', 'rate'])
        with self.assertRaises(ValidationError), self.cr.savepoint():
            rule.write({'calculation_method': 'fixed', 'category_id': self.category.id, 'rate': 6})
        self.assertEqual(rule.tier_ids.read(['kind', 'category_id', 'rate']), before)
        rule.write({'calculation_method': 'fixed', 'tier_ids': [Command.clear()],
                    'category_id': self.category.id, 'rate': 6})
        self.assertFalse(rule.tier_ids)
        self.assertEqual(rule.rate, 6)

    def test_fixed_existing_rules_and_snapshots_keep_their_meaning(self):
        self.assertEqual(self.rule.calculation_method, 'fixed')
        invoice = self.invoice(price=100)
        invoice.action_post()
        entry = self.entries(invoice)
        before = entry.read(['rule_id', 'rate', 'amount', 'personal_target', 'achievement_percent'])
        self.rule.write({'calculation_method': 'tiers', 'tier_ids': [Command.create({
            'kind': 'product', 'category_id': self.category.id, 'achievement_from': 0, 'rate': 8})]})
        self.assertEqual(entry.read(['rule_id', 'rate', 'amount', 'personal_target', 'achievement_percent']), before)
