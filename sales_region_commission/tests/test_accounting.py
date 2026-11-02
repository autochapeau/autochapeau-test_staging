from odoo import Command
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests import tagged
from . import test_commission as commission_tests


@tagged('post_install', '-at_install')
class TestCommissionAccrual(commission_tests.TestCommissionStudio):
    """Run the existing financial/scope suite with accruals enabled as well."""
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        company=cls.env.company
        cls.expense=cls.env['account.account'].create({'name':'Commission expense test','code':'CSACCEXP','account_type':'expense','company_id':company.id})
        cls.payable=cls.env['account.account'].create({'name':'Commission payable test','code':'CSACCPAY','account_type':'liability_current','company_id':company.id})
        cls.accrual_journal=cls.env['account.journal'].create({'name':'Commission accrual test','code':'CSAC','type':'general','company_id':company.id})
        company.write({'commission_journal_id':cls.accrual_journal.id,'commission_debit_account_id':cls.expense.id,'commission_credit_account_id':cls.payable.id,'commission_accrual_enabled':True})

    def test_balanced_expense_payable_and_idempotency(self):
        invoice=self.invoice(price=1000);invoice.action_post()
        entry=self.entries(invoice);move=entry.accrual_move_id
        self.assertEqual(move.state,'posted')
        self.assertEqual(move.commission_source_invoice_id,invoice)
        self.assertEqual(sum(move.line_ids.mapped('balance')),0)
        self.assertEqual(move.line_ids.filtered(lambda l:l.account_id==self.expense).debit,100)
        self.assertEqual(move.line_ids.filtered(lambda l:l.account_id==self.payable).credit,100)
        self.assertEqual(move.line_ids.partner_id,self.alice.partner_id)
        entry._accrue_commissions();entry._accrue_commissions()
        self.assertEqual(invoice.commission_account_move_ids,move)

    def test_partial_refund_uses_original_accounts_after_config_change(self):
        invoice=self.invoice(price=1000);invoice.action_post()
        replacement=self.env['account.account'].create({'name':'Replacement expense test','code':'CSACCEX2','account_type':'expense','company_id':self.env.company.id})
        self.env.company.commission_debit_account_id=replacement
        self.env.company.commission_accrual_enabled=False
        refund=invoice._reverse_moves([{'date':'2026-11-02','invoice_date':'2026-11-02'}])
        refund.invoice_line_ids.quantity=.25
        refund.action_post()
        move=self.entries(refund).accrual_move_id
        self.assertEqual(move.state,'posted')
        self.assertEqual(move.line_ids.filtered(lambda l:l.account_id==self.expense).credit,25)
        self.assertEqual(move.line_ids.filtered(lambda l:l.account_id==self.payable).debit,25)

    def test_reset_reverses_and_repost_creates_new_accrual(self):
        invoice=self.invoice();invoice.action_post()
        original=self.entries(invoice).accrual_move_id
        invoice.button_draft()
        self.assertEqual(original.state,'posted')
        self.assertEqual(original.commission_reversed_by_id.state,'posted')
        self.assertTrue(original.commission_reversed_by_id.commission_is_reversal)
        self.assertEqual(sum((original|original.commission_reversed_by_id).line_ids.filtered(lambda l:l.account_id==self.expense).mapped('balance')),0)
        invoice.action_post()
        self.assertNotEqual(self.entries(invoice).accrual_move_id,original)
        self.assertEqual(len(invoice.commission_account_move_ids),3)

    def test_generated_journals_and_lines_cannot_be_forged_or_changed(self):
        invoice=self.invoice();invoice.action_post()
        move=self.entries(invoice).accrual_move_id
        with self.assertRaises(UserError):move.button_draft()
        with self.assertRaises(UserError):move.line_ids[:1].write({'debit':999})
        with self.assertRaises(AccessError):move.write({'commission_source_invoice_id':False})
        with self.assertRaises(UserError):move._reverse_moves()
        with self.assertRaises(UserError):move.unlink()
        with self.assertRaises(UserError), self.env.cr.savepoint():
            self.env['account.move.line'].with_context(default_move_id=move.id,check_move_validity=False).create([
                {'name':'Forbidden debit','account_id':self.expense.id,'debit':10},
                {'name':'Forbidden credit','account_id':self.payable.id,'credit':10},
            ])

    def test_invalid_accounting_configuration(self):
        with self.assertRaises(ValidationError),self.env.cr.savepoint():self.env.company.commission_credit_account_id=self.expense
        with self.assertRaises(ValidationError),self.env.cr.savepoint():self.env.company.commission_journal_id=self.company_data['default_journal_sale']
        with self.assertRaises(ValidationError),self.env.cr.savepoint():self.env.company.commission_debit_account_id=False
        with self.assertRaises(AccessError):self.env.company.with_user(self.alice).write({'commission_accrual_enabled':False})

    def test_review_zero_and_disabled_do_not_book(self):
        self.rule.active=False
        invoice=self.invoice();invoice.action_post()
        self.assertFalse(self.entries(invoice).accrual_move_id)
        self.rule.active=True;self.rule.rate=0
        zero=self.invoice();zero.action_post()
        self.assertEqual(self.entries(zero).accounting_status,'zero')
        self.assertFalse(self.entries(zero).accrual_move_id)
        self.rule.rate=10;self.env.company.commission_accrual_enabled=False
        disabled=self.invoice();disabled.action_post()
        self.assertFalse(self.entries(disabled).accrual_move_id)
        with self.assertRaises(AccessError):self.entries(disabled).with_user(self.admin).action_accrue()

    def test_historical_calculation_does_not_silently_book(self):
        self.env.company.commission_accrual_enabled=False
        invoice=self.invoice();invoice.action_post()
        self.env.company.commission_accrual_enabled=True
        wizard=self.env['sales.commission.calculate'].with_user(self.admin).create({'date_from':'2026-11-02','date_to':'2026-11-02'})
        wizard.action_calculate()
        self.assertFalse(self.entries(invoice).accrual_move_id)
        self.admin.groups_id |= self.env.ref('account.group_account_manager')
        self.entries(invoice).with_user(self.admin).action_accrue()
        self.assertEqual(self.entries(invoice).accrual_move_id.state,'posted')

    def test_refund_of_pre_feature_invoice_never_debits_unbooked_liability(self):
        self.env.company.commission_accrual_enabled=False
        invoice=self.invoice();invoice.action_post()
        self.env.company.commission_accrual_enabled=True
        refund=invoice._reverse_moves([{'date':'2026-11-02','invoice_date':'2026-11-02'}]);refund.action_post()
        self.assertFalse(self.entries(refund).accrual_move_id)

    def test_payable_account_supports_standard_reconciliation(self):
        self.payable.write({'account_type':'liability_payable','reconcile':True})
        invoice=self.invoice();invoice.action_post()
        payable_line=self.entries(invoice).accrual_move_id.line_ids.filtered(lambda l:l.account_id==self.payable)
        self.assertTrue(payable_line.date_maturity)
        payment=self.env['account.move'].create({'move_type':'entry','journal_id':self.accrual_journal.id,'line_ids':[
            Command.create({'name':'Local settlement test','account_id':self.payable.id,'partner_id':self.alice.partner_id.id,'date_maturity':invoice.date,'debit':10}),
            Command.create({'name':'Local settlement offset','account_id':self.expense.id,'credit':10}),
        ]})
        payment.action_post()
        (payable_line|payment.line_ids.filtered(lambda l:l.account_id==self.payable)).reconcile()
        self.assertTrue(payable_line.reconciled)

    def test_cancellation_preserves_one_posted_reversal(self):
        invoice=self.invoice();invoice.action_post()
        original=self.entries(invoice).accrual_move_id
        invoice.button_draft();invoice.button_cancel()
        self.assertEqual(original.state,'posted')
        self.assertEqual(original.commission_reversed_by_id.state,'posted')
        self.assertEqual(len(invoice.commission_account_move_ids),2)
