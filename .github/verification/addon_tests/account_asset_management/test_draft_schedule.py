from datetime import date
from unittest.mock import patch

from odoo import fields
from odoo.exceptions import UserError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged("post_install", "-at_install", "asset_draft_schedule")
class TestAssetDraftSchedule(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        company_partner = cls.env["res.partner"].with_context(no_vat_validation=True).create({
            "name": "QA Asset Schedule Company", "is_company": True,
            "country_id": cls.env.ref("base.us").id, "street": "QA Test Address",
            "vat": "US123456789", "company_registry": "QA-ASSET-ONLY",
        })
        cls.company = cls.env["res.company"].create({
            "name": "QA Asset Schedule Company", "currency_id": cls.env.ref("base.SAR").id,
            "partner_id": company_partner.id,
        })
        cls.env = cls.env(context=dict(cls.env.context, allowed_company_ids=cls.company.ids))
        asset_account, expense_account = cls.env["account.account"].create([
            {"name": "QA Fixed assets", "code": "QAFIX", "account_type": "asset_fixed", "company_id": cls.company.id},
            {"name": "QA Depreciation expense", "code": "QADEP", "account_type": "expense_depreciation", "company_id": cls.company.id},
        ])
        journal = cls.env["account.journal"].create({
            "name": "QA Asset Schedule", "code": "QASCH", "type": "general", "company_id": cls.company.id,
        })
        cls.profile = cls.env["account.asset.profile"].create({
            "name": "QA scheduled monthly asset",
            "company_id": cls.env.company.id,
            "journal_id": journal.id,
            "account_asset_id": asset_account.id,
            "account_depreciation_id": asset_account.id,
            "account_expense_depreciation_id": expense_account.id,
            "method": "linear", "method_time": "number",
            "method_number": 3, "method_period": "month", "prorata": False,
        })

    def asset(self):
        return self.env["account.asset"].create({
            "name": "QA draft schedule", "profile_id": self.profile.id,
            "purchase_value": 300, "date_start": date(2030, 1, 1),
            "company_id": self.env.company.id,
        })

    def lines(self, asset):
        return asset.depreciation_line_ids.filtered(
            lambda line: line.type == "depreciate" and not line.init_entry
        ).sorted("line_date")

    def test_activation_creates_complete_draft_schedule(self):
        asset = self.asset()
        self.assertFalse(self.lines(asset).move_id)
        asset.validate()
        lines = self.lines(asset)
        self.assertEqual(len(lines), 3)
        self.assertEqual(len(lines.move_id), 3)
        self.assertEqual(set(lines.move_id.mapped("state")), {"draft"})
        self.assertEqual(set(lines.move_id.mapped("auto_post")), {"at_date"})
        self.assertFalse(any(lines.mapped("move_check")))
        self.assertEqual(asset.state, "open")
        self.assertEqual(asset.value_residual, 300)
        self.assertEqual(asset.value_depreciated, 0)
        for move in lines.move_id:
            self.assertEqual(sum(move.line_ids.mapped("balance")), 0)

    def test_repeated_activation_and_generation_do_not_duplicate(self):
        asset = self.asset()
        asset.validate()
        moves = self.lines(asset).move_id
        asset.validate()
        self.lines(asset).create_move()
        self.assertEqual(self.lines(asset).move_id, moves)

    def test_recompute_replaces_drafts_and_preserves_posted_history(self):
        asset = self.asset()
        asset.validate()
        first = self.lines(asset)[0]
        old_future = (self.lines(asset) - first).move_id
        with patch.object(fields.Date, "context_today", return_value=first.line_date):
            first.create_move()
        posted = first.move_id
        posted_values = (posted.name, posted.date, posted.line_ids.ids)
        self.assertTrue(first.move_check)
        self.assertEqual(asset.value_residual, 200)
        asset.compute_depreciation_board()
        self.assertFalse(old_future.exists())
        self.assertTrue(posted.exists())
        self.assertEqual((posted.name, posted.date, posted.line_ids.ids), posted_values)
        self.assertEqual(len(self.lines(asset).move_id), 3)
        self.assertEqual(len(self.lines(asset).filtered("move_check")), 1)
        self.assertEqual(asset.value_residual, 200)

    def test_soft_post_only_posts_due_entries(self):
        asset = self.asset()
        asset.validate()
        lines = self.lines(asset)
        with patch.object(fields.Date, "context_today", return_value=lines[0].line_date):
            posted = lines.move_id._post(soft=True)
        self.assertEqual(posted, lines[0].move_id)
        self.assertEqual((lines - lines[0]).move_id.mapped("state"), ["draft", "draft"])
        self.assertEqual(asset.value_residual, 200)

    def test_future_posting_cannot_be_forced_by_disabling_auto_post(self):
        asset = self.asset()
        asset.validate()
        move = self.lines(asset)[0].move_id
        move.auto_post = "no"
        with self.assertRaises(UserError), self.cr.savepoint():
            move.action_post()
        self.assertEqual(move.state, "draft")

    def test_pausing_and_reactivating_asset_controls_schedule(self):
        asset = self.asset()
        asset.validate()
        moves = self.lines(asset).move_id
        asset.set_to_draft()
        self.assertEqual(set(moves.mapped("auto_post")), {"no"})
        with patch.object(fields.Date, "context_today", return_value=date(2031, 1, 1)):
            with self.assertRaises(UserError), self.cr.savepoint():
                moves[0].action_post()
        asset.validate()
        self.assertEqual(self.lines(asset).move_id, moves)
        self.assertEqual(set(moves.mapped("auto_post")), {"at_date"})

    def test_final_post_closes_asset_and_reset_reopens_it(self):
        asset = self.asset()
        asset.validate()
        with patch.object(fields.Date, "context_today", return_value=date(2031, 1, 1)):
            moves = self.lines(asset).move_id
            moves._post(soft=True)
            self.assertEqual(asset.value_residual, 0)
            self.assertEqual(asset.state, "close")
            self.assertEqual(set(self.lines(asset).create_move()), set(moves.ids))
            moves[-1].button_draft()
        self.assertEqual(asset.state, "open")
        self.assertEqual(asset.value_residual, 100)

    def test_recompute_running_asset_does_not_recognize_drafts(self):
        asset = self.asset()
        asset.validate()
        old_moves = self.lines(asset).move_id
        asset.compute_depreciation_board()
        self.assertFalse(old_moves.exists())
        self.assertEqual(len(self.lines(asset).move_id), 3)
        self.assertEqual(asset.value_residual, 300)
        self.assertEqual(asset.state, "open")
