from odoo import Command
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests import Form, TransactionCase, tagged
from odoo.tests.common import new_test_user


@tagged("post_install", "-at_install")
class TestServiceMaterials(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env = cls.env(context=dict(cls.env.context, tracking_disable=True, mail_create_nosubscribe=True))
        cls.unit = cls.env.ref("uom.product_uom_unit")
        cls.dozens = cls.env.ref("uom.product_uom_dozen")
        cls.branch = cls.env["hr.department"].create({"name": "Material test branch", "department_type": "branche"})
        cls.warehouse = cls.env["stock.warehouse"].create({
            "name": "Material test warehouse", "code": "MATT", "branch_id": cls.branch.id,
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

    def test_part_snapshots_and_actual_usage_consumed_once(self):
        order = self._order()
        self.assertEqual(len(order.product_ids), 3)
        self.assertEqual(set(order.product_ids.part_id.ids), set((self.right | self.left).ids))
        self._start(order)
        self.assertFalse(order.picking_id.move_ids)
        right_film = order.product_ids.filtered(lambda line: line.part_id == self.right and line.product_id == self.film)
        right_film.quantity = 4
        order.action_finish_materials()
        self.assertEqual(self._available(self.film), 93)
        self.assertEqual(self._available(self.liquid), 99)
        self.assertEqual(order.material_picking_ids.state, "done")
        self.assertEqual(order.service_ids.state, "quality")
        self.assertTrue(order.materials_finished)
        order.service_ids.action_finish()
        self.assertEqual(self._available(self.film), 93)
        self.assertEqual(len(order.material_picking_ids), 1)
        with self.assertRaises(UserError):
            right_film.quantity = 5

    def test_existing_bom_lines_are_adopted_without_duplicates(self):
        products = [Command.create({"service_id": self.service.id, "product_id": bom.product_id.id,
                                    "quantity": bom.quantity}) for bom in self.service.bom_ids]
        order = self._order(products=products)
        order._sync_part_materials()
        self.assertEqual(len(order.product_ids), 3)
        self.assertTrue(all(order.product_ids.mapped("source_task_id")))
        self.assertEqual(len(order.product_ids.source_component_id), 3)

    def test_same_service_twice_keeps_two_material_sets(self):
        order = self._order(services=[self.service, self.service])
        self.assertEqual(len(order.product_ids), 6)
        self._start(order)
        order.action_finish_materials()
        self.assertEqual(self._available(self.film), 90)
        self.assertEqual(len(order.material_picking_ids), 2)

    def test_insufficient_stock_rolls_back_finish(self):
        order = self._order()
        order.product_ids.filtered(lambda line: line.product_id == self.film)[:1].quantity = 200
        self._start(order)
        with self.assertRaises(UserError), self.env.cr.savepoint():
            order.action_finish_materials()
        self.assertEqual(order.service_ids.state, "progress")
        self.assertFalse(order.material_picking_ids)
        self.assertEqual(self._available(self.film), 100)

    def test_units_are_converted_and_manual_products_stay_on_original_delivery(self):
        order = self._order(products=[Command.create({"product_id": self.liquid.id, "quantity": 2})])
        film_lines = order.product_ids.filtered(lambda line: line.product_id == self.film)
        film_lines[:1].write({"quantity": 1, "used_uom_id": self.dozens.id})
        self._start(order)
        self.assertEqual(len(order.picking_id.move_ids), 1)
        self.assertEqual(order.picking_id.move_ids.product_uom_qty, 2)
        order.action_finish_materials()
        self.assertEqual(self._available(self.film), 85)
        self.assertEqual(order.picking_id.state, "draft")

    def test_zero_usage_does_not_issue_material(self):
        order = self._order()
        order.product_ids.quantity = 0
        self._start(order)
        order.action_finish_materials()
        self.assertTrue(order.materials_finished)
        self.assertFalse(order.material_picking_ids)
        self.assertEqual(self._available(self.film), 100)

    def test_lot_selection_and_consumption(self):
        self.film.tracking = "lot"
        lot = self.env["stock.lot"].create({"name": "MAT-LOT", "product_id": self.film.id, "company_id": self.env.company.id})
        self.env["stock.quant"]._update_available_quantity(self.film, self.warehouse.lot_stock_id, 10, lot_id=lot)
        order = self._order()
        self._start(order)
        with self.assertRaises(UserError), self.env.cr.savepoint():
            order.action_finish_materials()
        order.product_ids.filtered(lambda line: line.product_id == self.film).lot_id = lot
        order.action_finish_materials()
        move_lines = order.material_picking_ids.move_line_ids.filtered(lambda line: line.product_id == self.film)
        self.assertEqual(move_lines.lot_id, lot)
        self.assertEqual(sum(move_lines.mapped("quantity")), 5)

    def test_rework_does_not_repeat_original_issue(self):
        order = self._order()
        self._start(order)
        order.action_finish_materials()
        task = order.service_ids
        task.state = "waiting"
        task.action_start()
        task.action_finish()
        self.assertEqual(self._available(self.film), 95)
        self.assertEqual(len(order.material_picking_ids), 1)

    def test_invalid_material_and_unit_are_rejected(self):
        with self.assertRaises(ValidationError), self.env.cr.savepoint():
            self.right_config.component_ids[:1].quantity = -1
        with self.assertRaises(ValidationError), self.env.cr.savepoint():
            self.right_config.component_ids[:1].product_id = self.service
        with self.assertRaises(ValidationError), self.env.cr.savepoint():
            self.right_config.component_ids[:1].product_uom_id = self.env.ref("uom.product_uom_meter")

    def test_issue_flags_cannot_be_forged(self):
        order = self._order()
        with self.assertRaises(UserError):
            order.service_ids.materials_issued = True

    def test_template_part_form_defaults_single_variant(self):
        template = self.service.product_tmpl_id
        roof = self.env["car.part"].create({"name": "Roof test"})
        with Form(self.env["car.service.part"].with_context(default_product_tmpl_id=template.id),
                  view="workorder_service_components.service_part_form") as form:
            form.part_id = roof
            with form.component_ids.new() as material:
                material.product_id = self.liquid
                material.quantity = 2
        part = form.record
        self.assertEqual(part.service_id, self.service)
        self.assertEqual(part.component_ids.service_id, self.service)
        self.assertIn(part, template.service_part_ids)

    def test_finish_requires_start_and_confirm(self):
        order = self._order()
        with self.assertRaises(UserError):
            order.action_start_materials()
        with self.assertRaises(UserError):
            order.service_ids.action_finish()
        self.assertEqual(self._available(self.film), 100)

    def test_changing_draft_service_removes_obsolete_snapshot(self):
        order = self._order()
        other = self.env["product.product"].create({"name": "Another service", "detailed_type": "service"})
        order.write({"service_ids": [Command.update(order.service_ids.id, {"product_id": other.id})]})
        self.assertFalse(order.product_ids)

    def test_draft_service_can_be_removed_with_its_snapshot(self):
        order = self._order()
        order.write({"service_ids": [Command.delete(order.service_ids.id)]})
        self.assertFalse(order.product_ids)

    def test_legacy_draft_delivery_is_rebuilt_before_consumption(self):
        order = self._order()
        order.product_ids.write({"source_task_id": False})
        # Simulate the delivery created by the previous module version.
        order.picking_id = order._create_delivery_picking()
        self.assertEqual(len(order.picking_id.move_ids), 3)
        order.state = "confirmed"
        order.action_start_materials()
        self.assertFalse(order.picking_id.move_ids)
        order.action_finish_materials()
        self.assertEqual(self._available(self.film), 95)

    def test_serial_consumption_uses_selected_serial(self):
        serial_product = self.env["product.product"].create({
            "name": "Serial test material", "detailed_type": "product", "tracking": "serial",
        })
        serial = self.env["stock.lot"].create({"name": "MAT-SERIAL", "product_id": serial_product.id, "company_id": self.env.company.id})
        self.env["stock.quant"]._update_available_quantity(serial_product, self.warehouse.lot_stock_id, 1, lot_id=serial)
        self.right_config.component_ids = [Command.create({"product_id": serial_product.id, "quantity": 1})]
        order = self._order()
        order.product_ids.filtered(lambda line: line.product_id == serial_product).lot_id = serial
        self._start(order)
        order.action_finish_materials()
        self.assertEqual(order.material_picking_ids.move_line_ids.filtered(lambda line: line.product_id == serial_product).lot_id, serial)

    def test_actual_confirmation_then_finish(self):
        slot = self.env["car.appointment.slot"].create({
            "date": "2099-01-15", "start_hour": 9, "duration": 1, "capacity": 5,
        })
        checkin = self.env["car.checkin"].create({
            "partner_id": self.customer.id, "vehicle_id": self.vehicle.id,
            "branch_id": self.branch.id, "state": "done",
        })
        appointment = self.env["car.appointment"].create({
            "appointment_slot_id": slot.id, "partner_id": self.customer.id,
            "vehicle_id": self.vehicle.id, "branch_id": self.branch.id, "car_checkin_id": checkin.id,
        })
        order = self._order()
        order.appointment_id = appointment
        order.action_confirm()
        self.assertEqual(order.state, "confirmed")
        self.assertFalse(order.picking_id.move_ids)
        order.action_start_materials()
        order.action_finish_materials()
        self.assertEqual(self._available(self.film), 95)

    def test_manager_can_finish_without_stock_administrator_access(self):
        user = new_test_user(self.env, login="material_test_manager", groups="work_orders.group_workshop_manager")
        self.staff.user_id = user
        order = self._order()
        self._start(order)
        self.assertFalse(user.has_group("stock.group_stock_user"))
        order.with_user(user).action_finish_materials()
        self.assertEqual(self._available(self.film), 95)

    def test_selected_lot_shortage_does_not_use_untracked_stock(self):
        self.film.tracking = "lot"
        lot = self.env["stock.lot"].create({"name": "MAT-LOW-LOT", "product_id": self.film.id, "company_id": self.env.company.id})
        self.env["stock.quant"]._update_available_quantity(self.film, self.warehouse.lot_stock_id, 1, lot_id=lot)
        order = self._order()
        order.product_ids.filtered(lambda line: line.product_id == self.film).lot_id = lot
        self._start(order)
        with self.assertRaises(UserError), self.env.cr.savepoint():
            order.action_finish_materials()
        self.assertFalse(order.material_picking_ids)
        self.assertEqual(order.service_ids.state, "progress")

    def test_legacy_completed_delivery_does_not_issue_again(self):
        order = self._order()
        order.product_ids.write({"source_task_id": False})
        picking = order._create_delivery_picking()
        order.picking_id = picking
        picking.action_confirm()
        picking.action_assign()
        picking.move_ids.picked = True
        picking._action_done()
        self.assertEqual(self._available(self.film), 95)
        order.state = "confirmed"
        order.action_start_materials()
        self.assertTrue(order.service_ids.materials_issued)
        order.service_ids.action_finish()
        self.assertEqual(self._available(self.film), 95)
        self.assertFalse(order.material_picking_ids)

    def test_existing_material_can_be_grouped_without_copying_it(self):
        legacy = self.env["car.bom"].create({
            "service_id": self.service.id, "product_id": self.liquid.id, "quantity": 2,
        })
        self.assertIn(legacy, self.service.ungrouped_component_ids)
        self.assertNotIn(self.right_config.component_ids[:1], self.service.ungrouped_component_ids)
        count = len(self.service.bom_ids)
        legacy.service_part_id = self.right_config
        self.service.invalidate_recordset(["ungrouped_component_ids"])
        self.assertNotIn(legacy, self.service.ungrouped_component_ids)
        self.assertIn(legacy, self.right_config.component_ids)
        self.assertEqual(len(self.service.bom_ids), count)

    def test_combined_views_compile(self):
        for model, view in [
            ("product.product", "product.product_normal_form_view"),
            ("product.template", "product.product_template_only_form_view"),
            ("car.work.order", "work_orders.car_work_order_view_form"),
            ("car.service.part", "workorder_service_components.service_part_form"),
            ("car.service.component.batch", "workorder_service_components.service_component_batch_form"),
        ]:
            self.assertTrue(self.env[model].get_view(self.env.ref(view).id, "form")["arch"])

    def _categorized_materials(self):
        category = self.env["product.category"].create({"name": "Main films test", "is_main_material_category": True})
        child = self.env["product.category"].create({"name": "Child films test", "parent_id": category.id})
        grandchild = self.env["product.category"].create({"name": "Grandchild films test", "parent_id": child.id})
        self.film.categ_id = child
        self.liquid.categ_id = grandchild
        self.service.bom_ids.material_category_id = category
        return category

    def _batch_template(self):
        attribute = self.env["product.attribute"].create({"name": "Batch size test"})
        values = self.env["product.attribute.value"].create([
            {"name": name, "attribute_id": attribute.id} for name in ("Medium", "Large")
        ])
        return self.env["product.template"].create({
            "name": "Batch film service test", "detailed_type": "service",
            "attribute_line_ids": [Command.create({"attribute_id": attribute.id, "value_ids": [Command.set(values.ids)]})],
        })

    def _batch(self, template, category):
        return self.env["car.service.component.batch"].create({
            "product_tmpl_id": template.id, "service_ids": [Command.set(template.product_variant_ids.ids)],
            "part_id": self.right.id,
            "line_ids": [Command.create({"material_category_id": category.id, "product_id": self.film.id,
                                         "quantity": 4, "product_uom_id": self.unit.id})],
        })

    def test_batch_variants_independent_idempotent_and_existing_materials_kept(self):
        category = self._categorized_materials()
        template = self._batch_template()
        batch = self._batch(template, category)
        batch.action_apply()
        self.assertEqual(len(template.service_part_ids), 2)
        for variant in template.product_variant_ids:
            self.assertEqual(len(variant.bom_ids), 1)
            self.assertEqual(variant.bom_ids.material_category_id, category)
            self.assertEqual(variant.bom_ids.quantity, 4)
        self.env["car.bom"].create({"service_part_id": template.service_part_ids[0].id,
                                    "product_id": self.liquid.id, "quantity": 2})
        batch.line_ids.quantity = 6
        batch.action_apply()
        self.assertEqual(len(template.service_component_ids), 3)
        lines = template.service_component_ids.filtered(lambda line: line.product_id == self.film)
        lines[0].quantity = 7
        self.assertEqual(lines[1].quantity, 6)

    def test_batch_rejects_foreign_variant_without_partial_changes(self):
        category = self._categorized_materials()
        template = self._batch_template()
        batch = self._batch(template, category)
        batch.service_ids = self.service | template.product_variant_ids
        with self.assertRaises(ValidationError), self.env.cr.savepoint():
            batch.action_apply()
        self.assertFalse(template.service_part_ids)

    def test_batch_form_and_category_filter(self):
        category = self._categorized_materials()
        template = self._batch_template()
        with Form(self.env["car.service.component.batch"].with_context(default_product_tmpl_id=template.id),
                  view="workorder_service_components.service_component_batch_form") as form:
            form.part_id = self.right
            for service in template.product_variant_ids:
                form.service_ids.add(service)
            with form.line_ids.new() as line:
                line.material_category_id = category
                line.product_id = self.liquid
                line.quantity = 3
                self.assertEqual(line.product_uom_id, self.unit)
        form.record.action_apply()
        self.assertEqual(len(template.service_component_ids), 2)

    def test_configuration_rejects_material_outside_category(self):
        category = self._categorized_materials()
        other = self.env["product.product"].create({"name": "Outside material test", "detailed_type": "product"})
        with self.assertRaises(ValidationError), self.env.cr.savepoint():
            self.right_config.component_ids[0].product_id = other
        batch = self._batch(self._batch_template(), category)
        with self.assertRaises(ValidationError), self.env.cr.savepoint():
            batch.line_ids.product_id = other

    def test_replacement_in_confirmed_and_progress_issues_actual_substitute(self):
        category = self._categorized_materials()
        order = self._order()
        line = order.product_ids.filtered(lambda item: item.product_id == self.film)[0]
        self.assertEqual(line.material_category_id, category)
        source = line.source_component_id
        order.picking_id = order._create_delivery_picking()
        order.state = "confirmed"
        line.product_id = self.liquid
        self.assertEqual(line.suggested_qty, 2)
        self.assertEqual(line.quantity, 2)
        order.action_start_materials()
        line.product_id = self.film
        line.product_id = self.liquid
        self.assertEqual(line.source_component_id, source)
        self.assertEqual(line.service_id, self.service)
        self.assertEqual(line.part_id, self.right)
        order.action_finish_materials()
        self.assertEqual(line.material_move_id.product_id, self.liquid)
        self.assertEqual(self._available(self.film), 97)
        self.assertEqual(self._available(self.liquid), 97)
        with self.assertRaises(UserError), self.env.cr.savepoint():
            line.product_id = self.film
        with self.assertRaises(UserError), self.env.cr.savepoint():
            line.material_category_id = False

    def test_replacement_rejects_other_category_and_category_tampering(self):
        self._categorized_materials()
        order = self._order()
        self._start(order)
        line = order.product_ids[0]
        other = self.env["product.product"].create({"name": "Other category test", "detailed_type": "product"})
        with self.assertRaises(ValidationError), self.env.cr.savepoint():
            line.product_id = other
        with self.assertRaises(UserError), self.env.cr.savepoint():
            line.material_category_id = other.categ_id
        with self.assertRaises(UserError), self.env.cr.savepoint():
            line.service_id = other

    def test_replacement_clears_lot_and_updates_unit(self):
        self._categorized_materials()
        self.film.tracking = "lot"
        lot = self.env["stock.lot"].create({"name": "Old replacement lot", "product_id": self.film.id, "company_id": self.env.company.id})
        order = self._order()
        self._start(order)
        line = order.product_ids.filtered(lambda item: item.product_id == self.film)[0]
        line.lot_id = lot
        replacement = self.env["product.product"].create({
            "name": "Length replacement test", "detailed_type": "product", "categ_id": self.liquid.categ_id.id,
            "uom_id": self.env.ref("uom.product_uom_meter").id,
            "uom_po_id": self.env.ref("uom.product_uom_meter").id,
        })
        line.product_id = replacement
        self.assertFalse(line.lot_id)
        self.assertEqual(line.used_uom_id, replacement.uom_id)

    def test_explicit_replacement_lot_is_validated_and_retained(self):
        self._categorized_materials()
        self.liquid.tracking = "lot"
        lot = self.env["stock.lot"].create({"name": "Replacement lot test", "product_id": self.liquid.id, "company_id": self.env.company.id})
        order = self._order()
        self._start(order)
        line = order.product_ids.filtered(lambda item: item.product_id == self.film)[0]
        line.write({"product_id": self.liquid.id, "lot_id": lot.id})
        self.assertEqual(line.lot_id, lot)
        line.write({"product_id": self.liquid.id, "quantity": 4})
        self.assertEqual(line.lot_id, lot)
        with self.assertRaises(ValidationError), self.env.cr.savepoint():
            line.write({"product_id": self.film.id, "lot_id": lot.id})

    def test_draft_resync_does_not_restore_replaced_product(self):
        self._categorized_materials()
        order = self._order()
        line = order.product_ids.filtered(lambda item: item.product_id == self.film)[0]
        line.product_id = self.liquid
        order._sync_part_materials()
        order._sync_part_materials()
        self.assertEqual(len(order.product_ids), 3)
        self.assertEqual(line.product_id, self.liquid)

    def test_legacy_product_lock_and_tags_preserved(self):
        order = self._order()
        self._start(order)
        line = order.product_ids[0]
        with self.assertRaises(UserError), self.env.cr.savepoint():
            line.product_id = self.liquid
        draft = self._order()
        tag = self.env["product.tag"].create({"name": "Legacy restricted test"})
        with self.assertRaises(ValidationError), self.env.cr.savepoint():
            draft.product_ids[0].tag_id = tag

    def test_categorized_replacement_uses_category_instead_of_legacy_tag(self):
        self._categorized_materials()
        tag = self.service.service_tag_id
        self.film.product_tag_ids = tag
        order = self._order()
        line = order.product_ids.filtered(lambda item: item.product_id == self.film)[0]
        self.assertEqual(line.tag_id, tag)
        self._start(order)
        line.product_id = self.liquid
        self.assertEqual(line.product_id, self.liquid)

    def test_workshop_manager_can_batch_configure_and_replace_before_issue(self):
        category = self._categorized_materials()
        user = new_test_user(self.env, login="material_batch_manager", groups="work_orders.group_workshop_manager")
        self.staff.user_id = user
        template = self._batch_template()
        batch = self._batch(template, category)
        batch.with_user(user).action_apply()
        self.assertEqual(len(template.service_part_ids), 2)
        order = self._order()
        self._start(order)
        line = order.product_ids.filtered(lambda item: item.product_id == self.film)[0]
        line.with_user(user).product_id = self.liquid
        order.with_user(user).action_finish_materials()
        self.assertEqual(line.material_move_id.product_id, self.liquid)

    def test_batch_rejects_ordinary_user(self):
        category = self._categorized_materials()
        user = new_test_user(self.env, login="material_batch_reader", groups="base.group_user")
        batch = self._batch(self._batch_template(), category)
        with self.assertRaises(AccessError), self.env.cr.savepoint():
            batch.with_user(user).action_apply()

    def test_replacement_form_preserves_quantities_and_source(self):
        self._categorized_materials()
        order = self._order()
        self._start(order)
        with Form(order, view="work_orders.car_work_order_view_form") as form:
            # Products occur twice in the combined form (draft and confirmed).
            # Form resolves the editable list for the current order state.
            with form.product_ids.edit(0) as line:
                original_quantity = line.quantity
                original_suggested = line.suggested_qty
                line.product_id = self.liquid
                self.assertEqual(line.quantity, original_quantity)
                self.assertEqual(line.suggested_qty, original_suggested)
        self.assertEqual(order.product_ids[0].product_id, self.liquid)

    def test_replacement_shortage_rolls_back_finish(self):
        self._categorized_materials()
        order = self._order()
        self._start(order)
        replacement = self.env["product.product"].create({
            "name": "Unavailable substitute test", "detailed_type": "product", "categ_id": self.film.categ_id.id,
        })
        line = order.product_ids[0]
        line.product_id = replacement
        with self.assertRaises(UserError), self.env.cr.savepoint():
            order.action_finish_materials()
        self.assertEqual(order.service_ids.state, "progress")
        self.assertFalse(order.service_ids.materials_issued)
        self.assertFalse(order.material_picking_ids)
        self.assertEqual(self._available(self.film), 100)

    def test_batch_requires_marked_category_and_rejects_duplicate_input(self):
        category = self._categorized_materials()
        template = self._batch_template()
        batch = self._batch(template, category)
        with self.assertRaises(ValidationError), self.env.cr.savepoint():
            batch.line_ids.material_category_id = self.film.categ_id
        batch.line_ids = [Command.create({"material_category_id": category.id, "product_id": self.film.id,
                                          "quantity": 2, "product_uom_id": self.unit.id})]
        with self.assertRaises(ValidationError), self.env.cr.savepoint():
            batch.action_apply()
        self.assertFalse(template.service_part_ids)

    def test_branch_availability_excludes_reservations_and_other_warehouses(self):
        other_branch = self.env["hr.department"].create({"name": "Other stock branch", "department_type": "branche"})
        other = self.env["stock.warehouse"].create({"name": "Other stock warehouse", "code": "AVOT", "branch_id": other_branch.id})
        shelf = self.env["stock.location"].create({"name": "Material shelf", "usage": "internal", "location_id": self.warehouse.lot_stock_id.id})
        Quant = self.env["stock.quant"]
        Quant._update_available_quantity(self.film, other.lot_stock_id, 500)
        Quant._update_available_quantity(self.film, shelf, 7)
        Quant._update_reserved_quantity(self.film, self.warehouse.lot_stock_id, 15)
        order = self._order()
        lines = order.product_ids.filtered(lambda line: line.product_id == self.film)
        self.assertEqual(lines.mapped("branch_available_qty"), [92, 92])
        self.assertEqual(lines.availability_warehouse_id, self.warehouse)
        self.assertFalse(any(lines.mapped("material_stock_shortage")))
        order.branch_id = other_branch
        self.assertEqual(lines.mapped("branch_available_qty"), [500, 500])
        self.assertEqual(lines.availability_warehouse_id, other)

    def test_branch_warning_totals_repeated_parts_and_does_not_reserve(self):
        self.env["stock.quant"]._update_available_quantity(self.film, self.warehouse.lot_stock_id, -96)
        order = self._order()
        lines = order.product_ids.filtered(lambda line: line.product_id == self.film)
        self.assertEqual(lines.mapped("branch_available_qty"), [4, 4])
        self.assertTrue(all(lines.mapped("material_stock_shortage")))
        message = lines[0]._onchange_warn_branch_stock()["warning"]
        self.assertEqual(message["title"], "Insufficient Branch Stock")
        self.assertIn(self.warehouse.name, message["message"])
        self.assertIn("5.00", message["message"])
        self.assertEqual(self._available(self.film), 4)
        lines[1].quantity = 1
        self.assertFalse(any(lines.mapped("material_stock_shortage")))
        self.assertFalse(lines[0]._onchange_warn_branch_stock())

    def test_branch_availability_unit_conversion(self):
        order = self._order()
        line = order.product_ids.filtered(lambda line: line.product_id == self.film)[0]
        line.write({"used_uom_id": self.dozens.id, "quantity": 8})
        self.assertAlmostEqual(line.branch_available_qty, 100 / 12, places=2)
        self.assertFalse(line.material_stock_shortage)  # 96 + 3 units.
        line.quantity = 9
        self.assertTrue(line.material_stock_shortage)
        self.assertIn(self.dozens.display_name, line.material_stock_warning)

    def test_branch_availability_selected_lot_ignores_untracked_and_other_lots(self):
        self.film.tracking = "lot"
        lot = self.env["stock.lot"].create({"name": "Availability lot", "product_id": self.film.id, "company_id": self.env.company.id})
        other = self.env["stock.lot"].create({"name": "Other availability lot", "product_id": self.film.id, "company_id": self.env.company.id})
        Quant = self.env["stock.quant"]
        Quant._update_available_quantity(self.film, self.warehouse.lot_stock_id, 2, lot_id=lot)
        Quant._update_available_quantity(self.film, self.warehouse.lot_stock_id, 40, lot_id=other)
        Quant._update_reserved_quantity(self.film, self.warehouse.lot_stock_id, 1, lot_id=lot)
        line = self._order().product_ids.filtered(lambda line: line.product_id == self.film)[0]
        line.lot_id = lot
        self.assertEqual(line.branch_available_qty, 1)
        self.assertTrue(line.material_stock_shortage)
        line.lot_id = other
        self.assertEqual(line.branch_available_qty, 40)
        self.assertFalse(line.material_stock_shortage)

    def test_branch_warning_handles_missing_configuration_and_legacy_products(self):
        order = self._order()
        line = order.product_ids[0]
        order.branch_id = False
        self.assertEqual(line.branch_available_qty, 0)
        self.assertFalse(line.material_stock_shortage)
        self.assertIn("no branch", line.material_stock_warning)
        branch = self.env["hr.department"].create({"name": "Branch without warehouse", "department_type": "branche"})
        order.branch_id = branch
        self.assertIn("No warehouse", line.material_stock_warning)
        legacy = self.env["product.product"].create({"name": "Legacy consumable availability", "detailed_type": "consu"})
        manual = self.env["car.workorder.product"].create({"workorder_id": order.id, "product_id": legacy.id, "quantity": 10})
        self.assertFalse(manual.material_stock_warning)
        self.assertEqual(manual.branch_available_qty, 0)

    def test_branch_availability_manager_without_stock_access(self):
        user = new_test_user(self.env, login="material_availability_manager", groups="work_orders.group_workshop_manager")
        self.staff.user_id = user
        order = self._order()
        line = order.product_ids[0].with_user(user)
        self.assertFalse(user.has_group("stock.group_stock_user"))
        self.assertEqual(line.branch_available_qty, 100)
        line.quantity = 150
        self.assertTrue(line.material_stock_shortage)
        self.assertTrue(line._onchange_warn_branch_stock()["warning"])

    def test_branch_availability_onchange_replacement_and_quantity_form(self):
        self._categorized_materials()
        self.env["stock.quant"]._update_available_quantity(self.liquid, self.warehouse.lot_stock_id, -99)
        order = self._order()
        self._start(order)
        with Form(order, view="work_orders.car_work_order_view_form") as form:
            with form.product_ids.edit(0) as line:
                line.product_id = self.liquid
                self.assertEqual(line.branch_available_qty, 1)
                self.assertTrue(line.material_stock_shortage)
                self.assertIn("Insufficient stock", line.material_stock_warning)
                line.quantity = 0
                self.assertFalse(line.material_stock_shortage)
        self.assertEqual(order.product_ids[0].quantity, 0)
        self.assertEqual(order.product_ids[0].product_id, self.liquid)

    def test_branch_availability_no_warning_after_issue_and_refresh(self):
        order = self._order()
        self._start(order)
        line = order.product_ids[0]
        self.assertEqual(line.branch_available_qty, 100)
        order.action_finish_materials()
        self.assertEqual(line.branch_available_qty, 95)
        self.assertFalse(line.material_stock_shortage)
        self.assertFalse(line.material_stock_warning)
        self.env["stock.quant"]._update_available_quantity(self.film, self.warehouse.lot_stock_id, 9)
        line.invalidate_recordset(["branch_available_qty"])
        self.assertEqual(line.branch_available_qty, 104)

    def test_branch_availability_unsaved_line_does_not_double_count_origin(self):
        order = self._order()
        saved = order.product_ids[0]
        self.env["stock.quant"]._update_available_quantity(self.film, self.warehouse.lot_stock_id, -95)
        line = self.env["car.workorder.product"].new({
            "workorder_id": order.id, "product_id": self.film.id, "quantity": 2,
            "used_uom_id": self.unit.id,
        }, origin=saved)
        self.assertEqual(line.branch_available_qty, 5)
        self.assertFalse(line.material_stock_shortage)  # 2 + the other part's 3.
