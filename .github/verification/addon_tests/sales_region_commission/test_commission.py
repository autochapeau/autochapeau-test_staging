from odoo import Command, fields
from odoo.tests import tagged
from odoo.tests.common import new_test_user, TransactionCase
from odoo.exceptions import AccessError, ValidationError


@tagged('post_install', '-at_install')
class TestCommissionStudio(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env = cls.env(su=True, context=dict(cls.env.context, tracking_disable=True, mail_create_nosubscribe=True, no_reset_password=True))
        company = cls.env.company
        Account=cls.env['account.account']
        revenue=Account.create({'name':'Commission test revenue','code':'CSREV','account_type':'income','company_id':company.id})
        receivable=Account.create({'name':'Commission test receivable','code':'CSREC','account_type':'asset_receivable','reconcile':True,'company_id':company.id})
        journal=cls.env['account.journal'].create({'name':'Commission test sales','code':'CSTS','type':'sale','company_id':company.id,'default_account_id':revenue.id})
        journal.edi_format_ids=[Command.clear()]
        cls.company_data={'company':company,'default_account_revenue':revenue,'default_journal_sale':journal}
        other_partner=cls.env['res.partner'].with_context(no_vat_validation=True).create({'name':'Commission isolated company', 'is_company':True, 'street':'Local test address', 'vat':'CS-TEST', 'company_registry':'CS-QA-CR'})
        other_company=cls.env['res.company'].create({'name':'Commission isolated company','partner_id':other_partner.id,'currency_id':company.currency_id.id})
        other_revenue=Account.create({'name':'Commission other revenue','code':'CSREV','account_type':'income','company_id':other_company.id})
        other_journal=cls.env['account.journal'].create({'name':'Commission other sales','code':'CSTS','type':'sale','company_id':other_company.id,'default_account_id':other_revenue.id})
        cls.company_data_2={'company':other_company,'default_account_revenue':other_revenue,'default_journal_sale':other_journal}
        cls.partner_a=cls.env['res.partner'].create({'name':'Commission test customer','property_account_receivable_id':receivable.id})
        brand=cls.env['fleet.vehicle.model.brand'].create({'name':'Commission test brand'})
        model=cls.env['fleet.vehicle.model'].create({'name':'Commission test model','brand_id':brand.id})
        cls.vehicle=cls.env['fleet.vehicle'].create({'model_id':model.id,'license_plate':'CS-LOCAL','vin_sn':'CSLOCALTEST000001','driver_id':cls.partner_a.id})
        cls.product_a=cls.env['product.product'].create({'name':'Commission base product','detailed_type':'consu','property_account_income_id':revenue.id})
        cls.tax_sale_a=cls.env['account.tax'].create({'name':'Commission test VAT','amount':15,'amount_type':'percent','type_tax_use':'sale','company_id':company.id})
        cls.alice = new_test_user(cls.env, login='commission_alice', groups='sales_region_commission.group_user', company_id=company.id, company_ids=[Command.set([company.id])])
        cls.bob = new_test_user(cls.env, login='commission_bob', groups='sales_region_commission.group_user', company_id=company.id, company_ids=[Command.set([company.id])])
        cls.manager = new_test_user(cls.env, login='commission_manager', groups='sales_region_commission.group_manager', company_id=company.id, company_ids=[Command.set([company.id])])
        cls.admin = new_test_user(cls.env, login='commission_admin', groups='sales_region_commission.group_admin', company_id=company.id, company_ids=[Command.set([company.id])])
        Team = cls.env['crm.team']
        cls.region = Team.create({'name':'Commission North', 'company_id':company.id, 'commission_level':'region', 'commission_manager_id':cls.manager.id})
        cls.area = Team.create({'name':'Commission North Area', 'company_id':company.id, 'commission_level':'area', 'commission_parent_id':cls.region.id})
        cls.branch = Team.create({'name':'Commission North Branch', 'company_id':company.id, 'commission_level':'branch', 'commission_parent_id':cls.area.id, 'member_ids':[Command.set(cls.alice.ids)]})
        cls.other = Team.create({'name':'Commission South Branch', 'company_id':company.id, 'member_ids':[Command.set(cls.bob.ids)]})
        cls.category = cls.env['product.category'].create({'name':'Commission film category'})
        cls.service_category = cls.env['commission.category'].create({'name':'Commission VIP'})
        cls.product = cls.env['product.product'].create({'name':'Commission film', 'detailed_type':'consu', 'property_account_income_id':revenue.id, 'categ_id':cls.category.id, 'taxes_id':[Command.clear()]})
        cls.service = cls.env['product.product'].create({'name':'Commission VIP service', 'detailed_type':'service', 'property_account_income_id':revenue.id, 'commission_category_id':cls.service_category.id, 'taxes_id':[Command.clear()]})
        cls.rule = cls.env['sales.commission.rule'].create({'name':'Alice film 10%', 'user_id':cls.alice.id, 'category_id':cls.category.id,'rate':10,'date_from':'2020-01-01'})
        cls.env['sales.commission.rule'].create({'name':'Alice VIP 7%', 'user_id':cls.alice.id, 'kind':'service','service_category_id':cls.service_category.id,'rate':7,'date_from':'2020-01-01'})
        cls.env['sales.commission.rule'].create({'name':'Bob film 5%', 'user_id':cls.bob.id, 'category_id':cls.category.id,'rate':5,'date_from':'2020-01-01'})

    def invoice(self, user=None, product=None, price=100, discount=0, quantity=1, tax=False, invoice_date='2026-11-02'):
        user = user or self.alice
        product = product or self.product
        order = self.env['sale.order'].create({'partner_id':self.partner_a.id,'user_id':user.id,'team_id':(self.branch if user == self.alice else self.other).id, 'order_type':'intern','vehicle_id':self.vehicle.id})
        sol = self.env['sale.order.line'].create({'order_id':order.id,'product_id':product.id,'product_uom_qty':1,'price_unit':price})
        return self.env['account.move'].create({'move_type':'out_invoice','partner_id':self.partner_a.id,'invoice_date':invoice_date,'journal_id':self.company_data['default_journal_sale'].id,'invoice_line_ids':[Command.create({'product_id':product.id,'quantity':quantity,'price_unit':price,'discount':discount,'account_id':self.company_data['default_account_revenue'].id,'tax_ids':[Command.set(tax.ids if tax else [])],'sale_line_ids':[Command.set(sol.ids)]})]})

    def entries(self, move):
        return self.env['sales.commission.entry'].search([('move_id','=',move.id)])

    def test_posted_net_discount_tax_and_original_salesperson(self):
        move = self.invoice(price=200, quantity=2, discount=25, tax=self.tax_sale_a)
        self.assertFalse(self.entries(move))
        move.invoice_user_id = self.bob
        move.action_post()
        entry = self.entries(move)
        self.assertEqual(entry.user_id,self.alice)
        self.assertAlmostEqual(entry.base,300)
        self.assertAlmostEqual(entry.amount,30)
        self.assertEqual(entry.status,'earned')
        move._snapshot_commissions()
        self.assertEqual(len(self.entries(move)),1)

    def test_service_category_has_its_own_rate(self):
        move=self.invoice(product=self.service,price=1000)
        move.action_post()
        self.assertEqual(self.entries(move).amount,70)

    def test_credit_note_uses_original_rate(self):
        move=self.invoice(price=1000)
        move.action_post()
        self.rule.rate=50
        refund=move._reverse_moves([{'date':'2026-11-02','invoice_date':'2026-11-02'}])
        refund.invoice_line_ids.quantity=.25
        refund.action_post()
        self.assertEqual(self.entries(move).amount,100)
        self.assertEqual(self.entries(refund).rate,10)
        self.assertEqual(self.entries(refund).amount,-25)
        self.assertEqual(self.entries(refund).origin_id,self.entries(move))

    def test_duplicate_product_refund_lines_preserve_exact_origin(self):
        move=self.invoice(price=100)
        move.invoice_line_ids.copy({'move_id':move.id,'price_unit':500,'sale_line_ids':[Command.set(move.invoice_line_ids.sale_line_ids.ids)]})
        move.action_post()
        refund=move._reverse_moves([{'date':'2026-11-02','invoice_date':'2026-11-02'}])
        refund.action_post()
        self.assertEqual(sum(self.entries(refund).mapped('amount')),-60)
        self.assertEqual(len(self.entries(refund).origin_id),2)
        self.assertEqual(set(self.entries(refund).mapped('status')),{'earned'})

    def test_missing_rule_and_unlinked_refund_require_review(self):
        self.rule.active=False
        move=self.invoice()
        move.action_post()
        self.assertEqual(self.entries(move).status,'review')
        self.assertEqual(self.entries(move).amount,0)
        refund=move._reverse_moves([{'date':'2026-11-02','invoice_date':'2026-11-02'}])
        refund.reversed_entry_id=False
        refund.action_post()
        self.assertEqual(self.entries(refund).status,'review')

    def test_reset_and_repost_and_refund_dependency(self):
        move=self.invoice()
        move.action_post()
        move.button_draft()
        self.assertFalse(self.entries(move))
        move.action_post()
        self.assertEqual(len(self.entries(move)),1)
        refund=move._reverse_moves([{'date':'2026-11-02','invoice_date':'2026-11-02'}])
        refund.action_post()
        with self.assertRaises(ValidationError), self.env.cr.savepoint():move.button_draft()
        refund.button_draft()
        move.button_draft()
        self.assertFalse(self.entries(move))

    def test_own_manager_and_admin_scope_in_search_and_dashboard(self):
        Ledger=self.env['sales.commission.entry']
        existing_admin_ids=set(Ledger.with_user(self.admin).search([]).ids)
        a=self.invoice(price=1000);a.action_post()
        b=self.invoice(user=self.bob,price=2000);b.action_post()
        self.assertEqual(Ledger.with_user(self.alice).search([]),self.entries(a))
        self.assertEqual(Ledger.with_user(self.manager).search([]),self.entries(a))
        self.assertEqual(set(Ledger.with_user(self.admin).search([]).ids),existing_admin_ids | set((self.entries(a)|self.entries(b)).ids))
        own=Ledger.with_user(self.alice).dashboard('2026-11-01')
        region=Ledger.with_user(self.manager).dashboard('2026-11-01')
        self.assertEqual(own['commission'],100)
        self.assertEqual(region['commission'],100)
        self.assertEqual([p['id'] for p in own['people']],[self.alice.id])
        with self.assertRaises(AccessError):Ledger.with_user(self.manager).dashboard('2026-11-01',self.other.id)
        with self.assertRaises(AccessError):self.entries(b).with_user(self.alice).read(['amount'])

    def test_cannot_forge_ledger_or_expand_own_region(self):
        move=self.invoice();move.action_post()
        entry=self.entries(move)
        with self.assertRaises(AccessError):entry.with_user(self.alice).write({'amount':99999})
        with self.assertRaises(AccessError):entry.with_user(self.admin).unlink()
        with self.assertRaises(AccessError):self.other.with_user(self.manager).write({'commission_manager_id':self.manager.id})
        with self.assertRaises(AccessError):self.rule.with_user(self.alice).write({'rate':99})

    def test_targets_rollup_without_double_count(self):
        Target=self.env['sales.commission.target']
        Target.create({'team_id':self.region.id,'month':'2026-11-01','amount':1000})
        Target.create({'team_id':self.branch.id,'month':'2026-11-01','amount':300})
        move=self.invoice(price=250);move.action_post()
        data=self.env['sales.commission.entry'].with_user(self.manager).dashboard('2026-11-01')
        self.assertEqual(data['target'],1000)
        self.assertEqual(data['net'],250)
        data=self.env['sales.commission.entry'].with_user(self.alice).dashboard('2026-11-01')
        self.assertEqual(data['target'],300)

    def test_invalid_rules_targets_and_hierarchy(self):
        with self.assertRaises(ValidationError),self.env.cr.savepoint():self.rule.copy({'name':'Overlapping'})
        with self.assertRaises(ValidationError),self.env.cr.savepoint():self.rule.rate=101
        with self.assertRaises(ValidationError),self.env.cr.savepoint():self.region.commission_parent_id=self.branch
        with self.assertRaises(ValidationError),self.env.cr.savepoint():self.env['sales.commission.target'].create({'team_id':self.branch.id,'month':'2026-11-02','amount':100})

    def test_date_boundaries(self):
        move=self.invoice(invoice_date='2026-10-31');move.action_post()
        ledger=self.env['sales.commission.entry'].with_user(self.alice)
        self.assertEqual(ledger.dashboard('2026-11-01')['commission'],0)
        self.assertEqual(ledger.dashboard('2026-10-01')['commission'],10)

    def test_company_isolation(self):
        move=self.invoice();move.action_post()
        company=self.company_data_2['company']
        self.env['sales.commission.entry'].sudo().create({'invoice_line_id':self.env['account.move.line'].create({'move_id':self.env['account.move'].create({'move_type':'entry','company_id':company.id,'journal_id':self.company_data_2['default_journal_sale'].id}).id,'name':'Other company line','account_id':self.company_data_2['default_account_revenue'].id}).id,'date':'2026-11-02','company_id':company.id,'user_id':self.alice.id,'status':'earned','base':999,'amount':999})
        data=self.env['sales.commission.entry'].with_user(self.alice).dashboard('2026-11-01')
        self.assertEqual(data['commission'],10)

    def test_revoked_manager_scope_is_immediate(self):
        move=self.invoice();move.action_post()
        Ledger=self.env['sales.commission.entry'].with_user(self.manager)
        self.assertEqual(Ledger.search_count([]),1)
        self.region.commission_manager_id=False
        self.assertEqual(Ledger.search_count([]),0)

    def test_leader_scope_and_reassignment_update_ledger_and_dashboard(self):
        self.region.write({'commission_manager_id':False,'user_id':self.manager.id})
        a=self.invoice(price=1000);a.action_post()
        b=self.invoice(user=self.bob,price=1000);b.action_post()
        Ledger=self.env['sales.commission.entry'].with_user(self.manager)
        self.assertEqual(Ledger.search([]),self.entries(a))
        self.assertEqual(Ledger.dashboard('2026-11-01')['commission'],100)
        self.assertIn(self.region.id,[t['id'] for t in Ledger.dashboard('2026-11-01')['teams']])
        self.region.user_id=self.bob
        self.assertFalse(Ledger.search([]))
        self.assertEqual(Ledger.dashboard('2026-11-01')['commission'],0)
        self.bob.groups_id |= self.env.ref('sales_region_commission.group_manager')
        self.assertIn(self.entries(a),self.env['sales.commission.entry'].with_user(self.bob).search([]))

    def test_leader_and_additional_manager_scopes_are_additive(self):
        self.other.user_id=self.manager
        a=self.invoice(price=1000);a.action_post()
        b=self.invoice(user=self.bob,price=1000);b.action_post()
        Ledger=self.env['sales.commission.entry'].with_user(self.manager)
        self.assertEqual(set(Ledger.search([]).ids),set((self.entries(a)|self.entries(b)).ids))
        self.region.commission_manager_id=False
        self.assertEqual(Ledger.search([]),self.entries(b))
        self.other.user_id=False
        self.assertFalse(Ledger.search([]))

    def test_leadership_never_grants_a_commission_role(self):
        self.other.user_id=self.alice
        self.branch.member_ids |= self.bob
        a=self.invoice();a.action_post()
        b=self.invoice(user=self.bob);b.action_post()
        self.assertFalse(self.alice.commission_visible_team_ids())
        self.assertEqual(self.env['sales.commission.entry'].with_user(self.alice).search([]),self.entries(a))
        outsider=new_test_user(self.env,login='commission_leader_no_role',groups='base.group_user')
        self.other.user_id=outsider
        with self.assertRaises(AccessError):self.env['sales.commission.entry'].with_user(outsider).dashboard('2026-11-01')

    def test_automatic_scope_obeys_selected_companies(self):
        other_company=self.company_data_2['company']
        self.manager.company_ids |= other_company
        self.region.write({'commission_manager_id':False,'user_id':self.manager.id})
        foreign=self.env['crm.team'].create({'name':'Foreign leadership scope','company_id':other_company.id,'user_id':self.manager.id})
        current=self.manager.with_user(self.manager).with_context(allowed_company_ids=self.env.company.ids)
        self.assertIn(self.branch.id,current.commission_visible_team_ids())
        self.assertNotIn(foreign.id,current.commission_visible_team_ids())
        switched=current.with_context(allowed_company_ids=other_company.ids)
        self.assertIn(foreign.id,switched.commission_visible_team_ids())
        self.assertNotIn(self.branch.id,switched.commission_visible_team_ids())

    def test_manager_cannot_assign_themselves_as_team_leader(self):
        with self.assertRaises(AccessError):self.other.with_user(self.manager).write({'user_id':self.manager.id})

    def test_leader_of_empty_and_shared_teams_can_select_them(self):
        self.region.write({'commission_manager_id':False,'user_id':self.manager.id})
        shared=self.env['crm.team'].create({'name':'Shared leadership team','company_id':False,'user_id':self.manager.id})
        Ledger=self.env['sales.commission.entry'].with_user(self.manager)
        choices={t['id'] for t in Ledger.dashboard('2026-11-01')['teams']}
        self.assertTrue({self.region.id,shared.id} <= choices)
        self.assertEqual(Ledger.dashboard('2026-11-01',self.region.id)['count'],0)
        self.region.active=False
        self.assertIn(self.region.id,self.manager.commission_visible_team_ids())

    def test_historical_retry_preserves_calculated_snapshots(self):
        self.rule.active=False
        move=self.invoice();move.action_post()
        self.rule.active=True
        wizard=self.env['sales.commission.calculate'].with_user(self.admin).create({'date_from':'2026-11-02','date_to':'2026-11-02'})
        wizard.action_calculate()
        self.assertEqual(self.entries(move).amount,10)
        self.rule.rate=50
        wizard.action_calculate()
        self.assertEqual(self.entries(move).amount,10)
        with self.assertRaises(AccessError):wizard.with_user(self.alice).action_calculate()

    def test_ambiguous_salespeople_are_reviewed(self):
        a=self.invoice();b=self.invoice(user=self.bob)
        a.invoice_line_ids.sale_line_ids |= b.invoice_line_ids.sale_line_ids
        a.action_post()
        self.assertEqual(self.entries(a).status,'review')
        self.assertFalse(self.entries(a).user_id)
        self.assertEqual(self.entries(a).amount,0)

    def test_full_foreign_currency_refund_reverses_original_commission(self):
        loss=self.env['account.account'].create({'name':'Commission FX test loss','code':'CSFXL','account_type':'expense','company_id':self.env.company.id})
        journal=self.env['account.journal'].create({'name':'Commission FX test journal','code':'CSFX','type':'general','company_id':self.env.company.id})
        self.env.company.write({'expense_currency_exchange_account_id':loss.id,'income_currency_exchange_account_id':self.company_data['default_account_revenue'].id,'currency_exchange_journal_id':journal.id})
        currency=self.env.ref('base.EUR')
        currency.active=True
        Rate=self.env['res.currency.rate']
        for day, rate in [('2026-10-31',.25),('2026-11-01',.5)]:
            row=Rate.search([('currency_id','=',currency.id),('company_id','=',self.env.company.id),('name','=',day)])
            if row:row.rate=rate
            else:Rate.create({'currency_id':currency.id,'company_id':self.env.company.id,'name':day,'rate':rate})
        move=self.invoice(price=100,invoice_date='2026-10-31')
        move.currency_id=currency
        move.action_post()
        original=self.entries(move)
        self.assertEqual(original.amount,self.env.company.currency_id.round(original.base*.1))
        refund=move._reverse_moves([{'date':'2026-11-01','invoice_date':'2026-11-01'}])
        refund.action_post()
        self.assertEqual(self.entries(refund).amount,-original.amount)

    def test_unassigned_user_has_no_dashboard_access(self):
        user=new_test_user(self.env,login='commission_no_role',groups='base.group_user')
        with self.assertRaises(AccessError):self.env['sales.commission.entry'].with_user(user).dashboard('2026-11-01')

    def test_nonoverlapping_rules_and_effective_dates(self):
        self.rule.date_to='2026-10-31'
        self.rule.copy({'name':'November rate','date_from':'2026-11-01','date_to':False,'rate':20})
        old=self.invoice(invoice_date='2026-10-31');old.action_post()
        new=self.invoice(invoice_date='2026-11-01');new.action_post()
        self.assertEqual(self.entries(old).amount,10)
        self.assertEqual(self.entries(new).amount,20)

    def test_manager_aggregates_multiple_child_teams(self):
        a=self.invoice(price=1000);a.action_post()
        b=self.invoice(user=self.bob,price=2000);b.action_post()
        Ledger=self.env['sales.commission.entry'].with_user(self.manager)
        self.assertEqual(Ledger.search_count([]),1)
        self.other.commission_parent_id=self.area
        data=Ledger.dashboard('2026-11-01')
        self.assertEqual(data['net'],3000)
        self.assertEqual(data['commission'],200)
        self.assertEqual({p['id'] for p in data['people']},{self.alice.id,self.bob.id})
