from lxml import etree
from odoo import Command
from odoo.exceptions import AccessError, ValidationError
from odoo.tests import Form, TransactionCase, tagged
from odoo.tests.common import new_test_user


@tagged('post_install', '-at_install')
class TestCommissionUserTab(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env = cls.env(context=dict(cls.env.context, no_reset_password=True, tracking_disable=True))
        cls.operator = new_test_user(cls.env, login='commission_tab_operator', groups='base.group_system')
        cls.person = new_test_user(cls.env, login='commission_tab_person', groups='base.group_user')
        cls.outsider = new_test_user(cls.env, login='commission_tab_outsider', groups='sales_region_commission.group_manager')
        cls.region = cls.env['crm.team'].create({'name':'User tab region','company_id':cls.env.company.id,'commission_level':'region'})

    def test_role_selection_changes_real_groups_and_downgrades(self):
        user = self.person.with_user(self.operator)
        for role in ('user','manager','admin','user','none'):
            user.commission_access_role = role
            self.assertEqual(user.commission_access_role,role)
            self.assertEqual(user.has_group('sales_region_commission.group_user'),role!='none')
            self.assertEqual(user.has_group('sales_region_commission.group_manager'),role in ('manager','admin'))
            self.assertEqual(user.has_group('sales_region_commission.group_admin'),role=='admin')
        self.assertTrue(user.has_group('sales_team.group_sale_salesman'))

    def test_no_self_elevation(self):
        with self.assertRaises(AccessError):self.person.with_user(self.person).write({'commission_access_role':'admin'})
        with self.assertRaises(AccessError):self.person.with_user(self.outsider).write({'commission_region_ids':[Command.set(self.region.ids)]})

    def test_assign_and_clear_regions_from_user(self):
        user = self.person.with_user(self.operator)
        user.write({'commission_access_role':'manager','commission_region_ids':[Command.set(self.region.ids)]})
        self.assertEqual(self.region.commission_manager_id,self.person)
        self.assertIn(self.region.id,self.person.commission_visible_team_ids())
        user.commission_region_ids=[Command.clear()]
        self.assertFalse(self.region.commission_manager_id)
        self.assertFalse(self.person.commission_visible_team_ids())

    def test_direct_group_assignment_updates_role(self):
        self.person.write({'groups_id':[Command.link(self.env.ref('sales_region_commission.group_admin').id)]})
        self.assertEqual(self.person.commission_access_role,'admin')
        self.assertFalse(self.person.commission_can_book_accruals)
        self.person.groups_id |= self.env.ref('account.group_account_manager')
        self.assertTrue(self.person.commission_can_book_accruals)

    def test_view_has_separate_tab_and_hides_duplicate_selector(self):
        view = self.env['res.users'].with_user(self.operator).get_view(view_id=self.env.ref('base.view_users_form').id,view_type='form')
        arch = etree.fromstring(view['arch'])
        self.assertTrue(arch.xpath("//page[@name='commission_access']//field[@name='commission_access_role']"))
        role_ids=sorted(self.env.ref('sales_region_commission.group_'+role).id for role in ('user','manager','admin'))
        name='sel_groups_'+'_'.join(map(str,role_ids))
        selectors=arch.xpath("//field[@name='%s']" % name)
        self.assertTrue(selectors)
        self.assertTrue(all(node.get('invisible')=='1' for node in selectors))

    def test_form_save_round_trip_keeps_selected_role(self):
        user=self.person.with_user(self.operator).with_context(uid=self.operator.id)
        with Form(user,view='base.view_users_form') as form:
            form.commission_access_role='manager'
        self.assertEqual(user.commission_access_role,'manager')
        with Form(user,view='base.view_users_form') as form:
            form.commission_access_role='none'
        self.assertFalse(user.has_group('sales_region_commission.group_user'))

    def test_navigation_respects_roles_and_keeps_guide_available(self):
        menus = self.env['ir.ui.menu']
        ref = lambda name: self.env.ref('sales_region_commission.menu_' + name).id
        workspace = {ref(name) for name in ('root','dashboard','ledger','targets','rules','guide')}
        configuration = {ref(name) for name in ('teams','calculate','service_category')}
        restricted = {ref('user_access'), ref('accounting_settings')}
        for role in ('user','manager','admin','none'):
            self.person.with_user(self.operator).commission_access_role = role
            visible = menus.with_user(self.person)._visible_menu_ids()
            if role == 'none':
                self.assertFalse(workspace & visible)
            else:
                self.assertTrue(workspace <= visible)
                self.assertFalse(restricted & visible)
                if role == 'admin':
                    self.assertTrue(configuration <= visible)
                else:
                    self.assertFalse(configuration & visible)
        self.assertEqual(self.env.ref('sales_region_commission.guide_action').tag, 'sales_region_commission.guide')
        self.assertEqual(self.env.ref('sales_region_commission.menu_root').web_icon, 'sales_region_commission,static/description/icon.png')
        self.assertEqual([kind for view_id, kind in self.env.ref('sales_region_commission.team_action').views], ['tree','form'])
