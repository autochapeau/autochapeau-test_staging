from lxml import etree

from odoo import Command
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests import Form, TransactionCase, tagged
from odoo.tests.common import new_test_user


@tagged("post_install", "-at_install")
class TestMaintenanceParts(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env = cls.env(context=dict(cls.env.context, tracking_disable=True, mail_create_nosubscribe=True))
        cls.unit = cls.env.ref("uom.product_uom_unit")
        cls.dozens = cls.env.ref("uom.product_uom_dozen")
        cls.branch = cls.env["hr.department"].create({"name": "Material test branch", "department_type": "branche"})
        cls.warehouse = cls.env["stock.warehouse"].create({
            "name": "Material test warehouse", "code": "MNTP", "branch_id": cls.branch.id,
            "company_id": cls.env.company.id,
        })
        cls.staff = cls.env["hr.employee"].create({"name": "Material technician", "is_technician": True, "branch_id": cls.branch.id})
        cls.customer = cls.env["res.partner"].create({"name": "Material test customer"})
        brand = cls.env["fleet.vehicle.model.brand"].create({"name": "Material test brand"})
        model = cls.env["fleet.vehicle.model"].create({"name": "Material test car", "brand_id": brand.id})
        cls.vehicle = cls.env["fleet.vehicle"].create({"model_id": model.id, "license_plate": "MAT-TEST"})
        cls.service = cls.env["product.product"].create({"name": "Film installation test", "detailed_type": "service"})
        cls.film = cls.env["product.product"].create({"name": "Film material test", "detailed_type": "product", "uom_id": cls.unit.id, "uom_po_id": cls.unit.id})
        cls.liquid = cls.env["product.product"].create({"name": "Liquid material test", "detailed_type": "product", "uom_id": cls.unit.id, "uom_po_id": cls.unit.id})
        cls.right = cls.env["car.part"].create({"name": "Right door test"})
        cls.left = cls.env["car.part"].create({"name": "Left door test"})
        cls.right_config = cls.env["car.service.part"].create({
            "part_id": cls.right.id, "service_id": cls.service.id,
            "component_ids": [Command.create({"product_id": cls.film.id, "quantity": 2}),
                              Command.create({"product_id": cls.liquid.id, "quantity": 1})],
        })
        cls.left_config = cls.env["car.service.part"].create({
            "part_id": cls.left.id, "service_id": cls.service.id,
            "component_ids": [Command.create({"product_id": cls.film.id, "quantity": 3})],
        })
        cls.env["stock.quant"]._update_available_quantity(cls.film, cls.warehouse.lot_stock_id, 100)
        cls.env["stock.quant"]._update_available_quantity(cls.liquid, cls.warehouse.lot_stock_id, 100)

    def _order(self, services=None, products=None):
        return self.env["car.work.order"].create({
            "partner_id": self.customer.id, "vehicle_id": self.vehicle.id,
            "branch_id": self.branch.id, "company_id": self.env.company.id,
            "service_ids": [Command.create({"product_id": service.id, "staff_ids": [Command.set(self.staff.ids)]})
                            for service in (services or self.service)],
            "product_ids": products or [],
        })

    def _start(self, order):
        # Exercise the actual delivery builder separately from the unrelated
        # appointment/check-in validation in action_confirm.
        order.picking_id = order._create_delivery_picking()
        order.state = "confirmed"
        order.action_start_materials()

    def _available(self, product):
        return self.env["stock.quant"]._get_available_quantity(product, self.warehouse.lot_stock_id)

    def _source(self, issue=True, dozens=False):
        self.film.standard_price = 10
        self.liquid.standard_price = 20
        sale = self.env["sale.order"].create({
            "partner_id": self.customer.id, "vehicle_id": self.vehicle.id,
            "order_type": "intern", "branch_id": self.branch.id,
            "warehouse_id": self.warehouse.id,
            "order_line": [Command.create({"product_id": self.service.id, "price_unit": 500})],
        })
        sale.write({"state": "sale"})
        order = self._order()
        order.sale_order_id = sale
        order.product_ids.filtered(lambda row: row.part_id == self.right and row.product_id == self.film).quantity = 4
        if dozens:
            order.product_ids.filtered(lambda row: row.part_id == self.right and row.product_id == self.film).write({"quantity": 1, "used_uom_id": self.dozens.id})
        self._start(order)
        if issue:
            order.action_finish_materials()
        return sale, order

    def _wizard(self, sale, order, parts=None):
        return self.env["maintenance.claim.wizard"].create({
            "sale_order_id": sale.id, "service_line_id": sale.order_line.id,
            "source_task_id": order.service_ids.id,
            "selected_part_ids": [Command.set((parts if parts is not None else self.right | self.left).ids)],
        })

    def _claim(self, wizard):
        return self.env["maintenance.claim"].browse(wizard.action_confirm()["res_id"])

    def test_two_parts_actual_cost_and_historical_valuation(self):
        sale, order = self._source()
        self.film.standard_price = 99
        self.right_config.component_ids.filtered(lambda row: row.product_id == self.film).quantity = 55
        claim = self._claim(self._wizard(sale, order))
        self.assertEqual(claim.source_workorder_id, order)
        self.assertEqual(claim.part_ids.vehicle_part_id, self.right | self.left)
        self.assertEqual(len(claim.part_ids), 3)
        self.assertAlmostEqual(claim.charge_cost, 90)  # actual film (4+3)*10 + liquid 1*20
        self.assertEqual(sum(claim.part_ids.filtered(lambda row: row.product_id == self.film).mapped("quantity")), 7)
        self.assertTrue(all(claim.part_ids.mapped("include")))
        self.assertTrue(claim.problem_location)

    def test_one_part_excludes_other_part_materials(self):
        sale, order = self._source()
        claim = self._claim(self._wizard(sale, order, self.left))
        self.assertAlmostEqual(claim.charge_cost, 30)
        self.assertEqual(claim.part_ids.vehicle_part_id, self.left)

    def test_unissued_service_rejected(self):
        sale, order = self._source(issue=False)
        with self.assertRaises(UserError):
            self._claim(self._wizard(sale, order))

    def test_foreign_workorder_and_forged_part_rejected(self):
        sale, order = self._source()
        other_sale, other_order = self._source()
        with self.assertRaises(UserError):
            self._claim(self._wizard(sale, other_order))
        foreign = self.env["car.part"].create({"name": "Unperformed part"})
        with self.assertRaises(UserError):
            self._claim(self._wizard(sale, order, foreign))

    def test_empty_parts_rejected(self):
        sale, order = self._source()
        with self.assertRaises(UserError):
            self._claim(self._wizard(sale, order, self.env["car.part"]))

    def test_actual_snapshot_cannot_be_edited_or_removed(self):
        sale, order = self._source()
        claim = self._claim(self._wizard(sale, order))
        for values in ({"quantity": 500}, {"unit_cost": 1}, {"include": False}, {"source_material_id": False}):
            with self.assertRaises(UserError):
                claim.part_ids[:1].write(values)
        with self.assertRaises(UserError):
            claim.part_ids.unlink()
        with self.assertRaises(UserError):
            claim.write({"source_task_id": False})
        with self.assertRaises(UserError):
            self.env["maintenance.claim.part"].create({"claim_id": claim.id, "product_id": self.film.id})

    def test_maintenance_order_is_child_and_only_selected_parts_execute(self):
        sale, order = self._source()
        claim = self._claim(self._wizard(sale, order, self.left))
        claim.write({"fault_type": "technician", "quality_reason": "Actual usage test", "employee_id": self.staff.id})
        repair = claim._create_maintenance_sale_order()
        self.assertEqual(repair.related_sale_id, sale)
        self.assertIn(repair, sale.child_sale_ids)
        self.assertEqual(repair.order_line.product_id, self.service)
        self.assertEqual(repair.amount_total, 0)
        workorder = self._order()
        # Exercise the same hook with the sale available before material creation.
        workorder.product_ids.unlink()
        workorder.sale_order_id = repair
        workorder._sync_part_materials()
        self.assertEqual(workorder.product_ids.part_id, self.left)
        self.assertEqual(len(workorder.product_ids), 1)

    def test_missing_valuation_never_falls_back_to_current_price(self):
        sale, order = self._source()
        row = order.product_ids[:1]
        row.material_move_id.stock_valuation_layer_ids.sudo().unlink()
        with self.assertRaises(UserError):
            self._claim(self._wizard(sale, order))

    def test_base_units_from_actual_delivery(self):
        sale, order = self._source(dozens=True)
        claim = self._claim(self._wizard(sale, order, self.right))
        film = claim.part_ids.filtered(lambda row: row.product_id == self.film)
        self.assertEqual(film.quantity, 12)
        self.assertAlmostEqual(film.unit_cost, 10)
        self.assertAlmostEqual(claim.charge_cost, 140)

    def test_direct_estimated_request_rejected(self):
        sale, order = self._source()
        with self.assertRaises(UserError):
            self.env["maintenance.claim"].create({
                "origin_sale_id": sale.id, "origin_sale_line_id": sale.order_line.id,
                "problem_location": "Unverified manual request",
            })

    def test_sales_user_can_select_and_create_request(self):
        sale, order = self._source()
        user = new_test_user(self.env(context=dict(self.env.context, no_reset_password=True)), login="maintenance_request_sales", groups="sales_team.group_sale_salesman_all_leads")
        wizard = self._wizard(sale, order).with_user(user)
        self.assertIn(order.service_ids, wizard.available_task_ids)
        wizard.available_task_ids.read(["display_name"])
        claim = self._claim(wizard)
        self.assertEqual(claim.charge_cost, 90)
        with self.assertRaises(UserError):
            claim.with_user(user).write({"fault_type": "customer"})

    def test_customer_quality_confirmation_and_repeat_guard(self):
        sale, order = self._source()
        claim = self._claim(self._wizard(sale, order))
        self.env.user.groups_id |= self.env.ref("work_orders.group_quality_officer")
        claim.write({"fault_type": "customer", "quality_reason": "Customer misuse"})
        claim.action_confirm_cause()
        self.assertEqual(claim.state, "confirmed")
        self.assertEqual(claim.sale_order_id.related_sale_id, sale)
        self.assertFalse(claim.move_id)
        self.assertGreater(claim.sale_order_id.amount_total, 0)
        with self.assertRaises(UserError):
            claim.action_confirm_cause()
        self.assertEqual(len(sale.child_sale_ids), 1)

    def _configure_accounts(self):
        company = self.env.company
        def account(code, kind):
            return self.env["account.account"].create({"name": "Maintenance test " + code, "code": code, "account_type": kind, "company_id": company.id})
        company.write({
            "qa_fault_journal_id": self.env["account.journal"].create({"name": "Maintenance test", "code": "MNTP", "type": "general", "company_id": company.id}).id,
            "qa_fault_technician_account_id": account("MNT001", "asset_receivable").id,
            "qa_fault_company_account_id": account("MNT002", "expense").id,
            "qa_fault_offset_account_id": account("MNT003", "asset_current").id,
        })
        self.env.user.groups_id |= self.env.ref("work_orders.group_quality_officer")

    def test_technician_actual_split_posts_balanced_entry(self):
        self._configure_accounts()
        sale, order = self._source()
        claim = self._claim(self._wizard(sale, order))
        claim.write({"fault_type": "technician", "quality_reason": "Technician rework", "employee_id": self.staff.id,
                     "technician_cost": 60, "company_cost": 30})
        claim.action_confirm_cause()
        self.assertEqual(claim.move_id.state, "posted")
        self.assertAlmostEqual(sum(claim.move_id.line_ids.mapped("debit")), 90)
        self.assertAlmostEqual(sum(claim.move_id.line_ids.mapped("credit")), 90)
        self.assertEqual(claim.sale_order_id.amount_total, 0)
        self.assertEqual(claim.sale_order_id.related_sale_id, sale)
        self.assertEqual(claim.move_id.line_ids.filtered(lambda line: line.debit == 60).partner_id, self.staff.work_contact_id)

    def test_supplier_actual_cost_posts_to_company(self):
        self._configure_accounts()
        sale, order = self._source()
        supplier = self.env["res.partner"].create({"name": "Maintenance test supplier", "supplier_rank": 1})
        claim = self._claim(self._wizard(sale, order, self.left))
        claim.write({"fault_type": "supplier", "quality_reason": "Defective material", "supplier_id": supplier.id})
        claim.action_confirm_cause()
        self.assertEqual(claim.company_cost, 30)
        self.assertEqual(claim.technician_cost, 0)
        self.assertEqual(claim.move_id.state, "posted")
        self.assertEqual(claim.sale_order_id.amount_total, 0)

    def test_bad_split_rolls_back_before_suborder(self):
        self._configure_accounts()
        sale, order = self._source()
        claim = self._claim(self._wizard(sale, order))
        claim.write({"fault_type": "technician", "quality_reason": "Bad split", "employee_id": self.staff.id,
                     "technician_cost": 100, "company_cost": 1})
        with self.assertRaises(UserError):
            claim.action_confirm_cause()
        self.assertFalse(sale.child_sale_ids)
        self.assertFalse(claim.move_id)


    def test_repair_materials_survive_deleted_bom_and_keep_actual_quantities(self):
        sale, order = self._source()
        claim = self._claim(self._wizard(sale, order, self.right))
        claim.write({"fault_type": "technician", "quality_reason": "Configuration changed", "employee_id": self.staff.id})
        repair = claim._create_maintenance_sale_order()
        self.service.service_part_ids.unlink()
        wo = self.env["car.work.order"].with_context(contract_upsell_sync=True).create({
            "partner_id": self.customer.id, "vehicle_id": self.vehicle.id,
            "sale_order_id": repair.id, "branch_id": self.branch.id, "company_id": self.env.company.id,
            "service_ids": [Command.create({"product_id": self.service.id, "staff_ids": [Command.set(self.staff.ids)]})],
        })
        self.assertEqual(wo.product_ids.part_id, self.right)
        self.assertEqual(len(wo.product_ids), 2)
        self.assertEqual(wo.product_ids.filtered(lambda row: row.product_id == self.film).quantity, 4)
        wo._sync_part_materials()
        self.assertEqual(len(wo.product_ids), 2)
        self._start(wo)
        wo.action_finish_materials()
        self.assertEqual(set(wo.material_picking_ids.move_ids.mapped("state")), {"done"})

    def test_tint_mapping_required_and_details_deduplicated(self):
        sale, order = self._source()
        self.service.product_tmpl_id.is_window_tinting = True
        glass = self.env["window.tint.glass.type"].create({"name": "Maintenance glass"})
        percentage = self.env["window.tint.percentage"].search([("percentage", "=", 30)], limit=1) or self.env["window.tint.percentage"].create({"name": "Maintenance tint", "percentage": 30})
        sale.order_line.tint_detail_ids = [Command.create({"glass_type_id": glass.id, "tint_percentage_id": percentage.id})]
        with self.assertRaises(UserError):
            self._claim(self._wizard(sale, order, self.right))
        self.right.maintenance_glass_type_id = glass
        claim = self._claim(self._wizard(sale, order, self.right))
        claim.write({"fault_type": "customer", "quality_reason": "Mapped glass"})
        repair = claim._create_maintenance_sale_order()
        self.assertEqual(len(repair.order_line.tint_detail_ids), 1)
        self.assertEqual(repair.order_line.tint_detail_ids.glass_type_id, glass)

