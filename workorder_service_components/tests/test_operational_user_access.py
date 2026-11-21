from lxml import etree

from odoo.exceptions import AccessError, ValidationError
from odoo.tests import Form, TransactionCase, tagged
from odoo.tests.common import new_test_user


@tagged("post_install", "-at_install")
class TestOperationalUserAccess(TransactionCase):
    def setUp(self):
        super().setUp()
        self.users = self.env["res.users"].with_context(no_reset_password=True)
        self.administrator = new_test_user(self.users.env, login="operational_access_administrator",
                                           groups="base.group_system")
        self.employee = new_test_user(self.users.env, login="operational_access_employee",
                                      groups="stock.group_stock_user")

    def test_tab_uses_real_permissions_and_preserves_other_groups(self):
        employee = self.employee.with_user(self.administrator).with_context(uid=self.administrator.id)
        sales_group = self.env.ref("sale_salesperson_access.group_edit_salesperson", raise_if_not_found=False)
        self.assertEqual(employee.operational_salesperson_permission_available, bool(sales_group))
        with Form(employee, view="base.view_users_form") as form:
            form.operational_material_preparer = True
            form.operational_quality_reviewer = True
            if sales_group:
                form.operational_edit_salesperson = True
        employee.invalidate_recordset(["groups_id"])
        expected = [
            self.env.ref("workorder_service_components.group_workshop_material_preparer"),
            self.env.ref("work_orders.group_quality_officer"),
            self.env.ref("stock.group_stock_user"),
        ]
        if sales_group:
            expected += [sales_group, self.env.ref("sales_team.group_sale_salesman")]
        self.assertTrue(all(group in employee.groups_id for group in expected))

        with Form(employee, view="base.view_users_form") as form:
            form.operational_material_preparer = False
            form.operational_quality_reviewer = False
            if sales_group:
                form.operational_edit_salesperson = False
        employee.invalidate_recordset(["groups_id"])
        self.assertFalse(employee.operational_material_preparer)
        self.assertFalse(employee.operational_quality_reviewer)
        self.assertFalse(employee.operational_edit_salesperson)
        self.assertIn(self.env.ref("stock.group_stock_user"), employee.groups_id)

    def test_inherited_access_and_non_admin_are_protected(self):
        manager = new_test_user(self.users.env, login="operational_access_quality_manager",
                                groups="work_orders.group_quality_manager").with_user(self.administrator)
        self.assertTrue(manager.operational_quality_reviewer)
        with self.assertRaises(ValidationError), self.env.cr.savepoint():
            manager.operational_quality_reviewer = False
        self.assertTrue(manager.operational_quality_reviewer)
        with self.assertRaises(AccessError), self.env.cr.savepoint():
            self.employee.with_user(self.employee).operational_material_preparer = True

    def test_help_is_visible_on_the_operational_forms(self):
        user_view = etree.fromstring(self.users.with_user(self.administrator).get_view(
            self.env.ref("base.view_users_form").id, "form")["arch"])
        page = user_view.xpath("//page[@name='operational_access']")[0]
        self.assertEqual(page.get("string"), "صلاحيات التشغيل")
        self.assertEqual(len(page.xpath(".//tbody/tr")), 3)
        self.assertIn("المهام المستنية فحص الجودة", " ".join(page.itertext()))
        warehouse_view = etree.fromstring(self.env["stock.warehouse"].get_view(
            self.env.ref("stock.view_warehouse").id, "form")["arch"])
        self.assertIn("طلبات تجهيز الخامات الجديدة", " ".join(warehouse_view.itertext()))
        if self.env.ref("sale_salesperson_access.view_order_form_salesperson_access", raise_if_not_found=False):
            sale_view = etree.fromstring(self.env["sale.order"].get_view(
                self.env.ref("sale.view_order_form").id, "form")["arch"])
            self.assertIn("تغيير مندوب البيع متاح", " ".join(sale_view.itertext()))
