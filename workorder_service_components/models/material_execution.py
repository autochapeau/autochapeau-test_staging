from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.tools.float_utils import float_compare

_ISSUE_TOKEN = object()


class WorkOrderProduct(models.Model):
    _inherit = "car.workorder.product"

    part_id = fields.Many2one("car.part", string="Vehicle Part", ondelete="restrict", index=True)
    source_component_id = fields.Many2one("car.bom", ondelete="set null", copy=False, index=True)
    source_task_id = fields.Many2one("car.workorder.service", ondelete="restrict", copy=False, index=True)
    material_move_id = fields.Many2one("stock.move", readonly=True, copy=False, ondelete="restrict")
    materials_issued = fields.Boolean(related="source_task_id.materials_issued")
    lot_id = fields.Many2one("stock.lot", string="Lot / Serial", check_company=True,
                             domain="[('product_id', '=', product_id)]", copy=False)
    company_id = fields.Many2one(related="workorder_id.company_id", store=True)

    @api.model
    def _values_from_component(self, service, component):
        vals = super()._values_from_component(service, component)
        vals.update(part_id=component.part_id.id, source_component_id=component.id)
        return vals

    def _apply_component(self, service, component):
        super()._apply_component(service, component)
        self.part_id = component.part_id
        self.source_component_id = component

    @api.onchange("part_id")
    def _onchange_vehicle_part(self):
        if self.product_id and self.service_id:
            component = self.service_id.bom_ids.filtered(
                lambda bom: bom.part_id == self.part_id and bom.product_id == self.product_id
            )[:1]
            if component:
                self._apply_component(self.service_id, component)

    @api.model_create_multi
    def create(self, vals_list):
        if any(vals.get("material_move_id") for vals in vals_list):
            raise UserError(_("Material movements are assigned only when finishing a service."))
        return super().create(vals_list)

    def write(self, vals):
        if "material_move_id" in vals and self.env.context.get("material_issue_token") is not _ISSUE_TOKEN:
            raise UserError(_("Material movements are assigned only when finishing a service."))
        if {"quantity", "lot_id"} & vals.keys():
            for order in self.workorder_id.sorted("id"):
                self.env.cr.execute("SELECT id FROM car_work_order WHERE id = %s FOR UPDATE", (order.id,))
            self.source_task_id.invalidate_recordset(["materials_issued"])
        protected = {"quantity", "product_id", "service_id", "part_id", "used_uom_id",
                     "suggested_qty", "source_task_id", "source_component_id", "workorder_id", "lot_id"}
        if protected & vals.keys() and self.filtered(lambda line: line.materials_issued or line.material_move_id.state == "done"):
            raise UserError(_("Issued materials cannot be changed. Use a stock return or a separate replacement delivery."))
        # The existing work-order lock keeps structural fields frozen. Actual usage
        # remains editable by workshop managers until the service is finished.
        if set(vals) <= {"quantity", "lot_id"} and self and all(
            line.source_task_id and line.workorder_id.state in ("confirmed", "progress")
            and line.source_task_id.state not in ("quality", "done", "cancel") for line in self
        ):
            return super(WorkOrderProduct, self.with_context(contract_upsell_sync=True)).write(vals)
        if {"part_id", "source_task_id", "source_component_id"} & vals.keys():
            if self.env.context.get("material_issue_token") is _ISSUE_TOKEN:
                return super(WorkOrderProduct, self.with_context(contract_upsell_sync=True)).write(vals)
            if self.filtered(lambda line: line.workorder_id.state != "new"):
                raise UserError(_("Material assignments cannot be changed after confirmation."))
        return super().write(vals)

    def unlink(self):
        if self.filtered(lambda line: line.materials_issued or line.material_move_id):
            raise UserError(_("Issued material lines cannot be deleted."))
        return super().unlink()

    @api.constrains("quantity", "used_uom_id", "product_id", "source_task_id", "service_id", "workorder_id", "lot_id")
    def _check_material_line(self):
        for line in self:
            if line.quantity < 0:
                raise ValidationError(_("Used quantities cannot be negative."))
            if line.lot_id and line.lot_id.product_id != line.product_id:
                raise ValidationError(_("The selected lot/serial belongs to another product."))
            if line.used_uom_id and line.used_uom_id.category_id != line.product_id.uom_id.category_id:
                raise ValidationError(_("The material unit must match the product's unit category."))
            if line.source_task_id and (
                line.source_task_id.workorder_id != line.workorder_id
                or line.source_task_id.product_id != line.service_id
            ):
                raise ValidationError(_("The material must belong to a matching service on this work order."))


class WorkOrder(models.Model):
    _inherit = "car.work.order"

    material_picking_ids = fields.One2many("stock.picking", "material_workorder_id", copy=False)
    material_picking_count = fields.Integer(compute="_compute_material_picking_count")
    materials_finished = fields.Boolean(compute="_compute_materials_finished")

    @api.depends("material_picking_ids")
    def _compute_material_picking_count(self):
        for order in self:
            order.material_picking_count = len(order.material_picking_ids)

    @api.depends("service_ids.materials_issued")
    def _compute_materials_finished(self):
        for order in self:
            order.materials_finished = bool(order.service_ids) and all(order.service_ids.mapped("materials_issued"))

    @api.model_create_multi
    def create(self, vals_list):
        # work_orders overrides create with a singleton dictionary signature.
        orders = self.browse()
        for vals in vals_list:
            orders |= super().create(vals)
        orders._sync_part_materials()
        return orders

    def write(self, vals):
        result = super().write(vals)
        if "service_ids" in vals and not self.env.context.get("skip_part_material_sync"):
            self.filtered(lambda order: order.state == "new")._sync_part_materials()
        return result

    def _sync_part_materials(self):
        """Snapshot materials and adopt existing appointment/upsell BOM lines.

        Match each task separately: the same product on two parts, or two
        occurrences of the same service, must remain separate material lines.
        """
        for order in self.filtered(lambda item: item.state == "new"):
            obsolete = order.product_ids.filtered(lambda line: line.source_task_id and line.service_id != line.source_task_id.product_id)
            obsolete.sudo().unlink()
            available = order.product_ids.filtered(lambda line: line.service_id and not line.source_task_id)
            for task in order.service_ids:
                existing = order.product_ids.filtered(lambda line: line.source_task_id == task)
                for bom in task.product_id.bom_ids:
                    if bom in existing.source_component_id:
                        continue
                    candidate = available.filtered(lambda line:
                        line.service_id == task.product_id and line.product_id == bom.product_id
                        and (not line.part_id or line.part_id == bom.part_id)
                        and (not line.source_component_id or line.source_component_id == bom)
                    )[:1]
                    if candidate:
                        candidate.write({
                            "source_task_id": task.id, "source_component_id": bom.id,
                            "part_id": bom.part_id.id, "suggested_qty": bom.quantity,
                            "used_uom_id": (candidate.used_uom_id or bom.product_uom_id or bom.product_id.uom_id).id,
                        })
                        available -= candidate
                    else:
                        vals = self.env["car.workorder.product"]._values_from_component(task.product_id, bom)
                        vals.update(workorder_id=order.id, source_task_id=task.id)
                        self.env["car.workorder.product"].create(vals)
            # Manual lines carrying a service are consumed with that service too.
            for line in available:
                tasks = order.service_ids.filtered(lambda task: task.product_id == line.service_id)
                if len(tasks) == 1:
                    line.source_task_id = tasks.id

    def action_confirm(self):
        self._sync_part_materials()
        return super().action_confirm()

    def _create_delivery_picking(self):
        picking = super()._create_delivery_picking()
        # Service materials have their own delivery at Finish. Leave only
        # separately sold products on the original draft delivery.
        if picking.state != "draft":
            raise UserError(_("The initial delivery must be draft when preparing work order materials."))
        self._reset_manual_delivery_moves(picking)
        return picking

    def _reset_manual_delivery_moves(self, picking):
        picking.move_ids.unlink()
        for line in self.product_ids.filtered(lambda item: not item.source_task_id):
            if line.product_id and line.quantity > 0:
                self.env["stock.move"].sudo().create({
                    "name": line.product_id.display_name,
                    "picking_id": picking.id,
                    "company_id": picking.company_id.id,
                    "product_id": line.product_id.id,
                    "product_uom_qty": line.quantity,
                    "product_uom": (line.used_uom_id or line.product_id.uom_id).id,
                    "location_id": picking.location_id.id,
                    "location_dest_id": picking.location_dest_id.id,
                })

    def _adopt_existing_materials(self):
        """Upgrade open orders without adding today's BOM to old snapshots.

        Already delivered quantities are never issued again. Ambiguous legacy
        services require review instead of silently charging the wrong task.
        """
        for order in self:
            pending = order.product_ids.filtered(lambda line: line.service_id and not line.source_task_id)
            if not pending:
                continue
            picking = order.picking_id.sudo()
            if picking and picking.state not in ("draft", "done", "cancel"):
                raise UserError(_("The existing delivery is reserved. Complete it or reset it to draft before finishing service materials."))
            for line in pending:
                tasks = order.service_ids.filtered(lambda task: task.product_id == line.service_id)
                if len(tasks) != 1:
                    raise UserError(_("An existing material line cannot be matched to a single service. Review this work order before finishing."))
                bom = line.service_id.bom_ids.filtered(lambda item: item.product_id == line.product_id)
                vals = {"source_task_id": tasks.id}
                if len(bom) == 1:
                    vals.update(source_component_id=bom.id, part_id=bom.part_id.id)
                line.sudo().with_context(material_issue_token=_ISSUE_TOKEN).write(vals)
                if picking.state == "done":
                    tasks.sudo().with_context(material_issue_token=_ISSUE_TOKEN).write({
                        "materials_issued": True, "material_picking_id": picking.id,
                    })
            if picking.state == "draft":
                order._reset_manual_delivery_moves(picking)

    def action_start_materials(self):
        self.ensure_one()
        if self.state not in ("confirmed", "progress"):
            raise UserError(_("Confirm the work order before starting services."))
        self._adopt_existing_materials()
        if self.state == "confirmed":
            self.action_progress()
        for task in self.service_ids.filtered(lambda item: item.state in ("waiting", "ready")):
            task.action_start()
        return True

    def action_finish_materials(self):
        self.ensure_one()
        if self.state != "progress":
            raise UserError(_("Start the work order before finishing services."))
        pending = self.service_ids.filtered(lambda item: not item.materials_issued)
        if pending.filtered(lambda item: item.state != "progress"):
            raise UserError(_("Start or resume all unfinished services before pressing Finish."))
        with self.env.cr.savepoint():
            for task in pending:
                task.action_finish()
        return True

    def action_view_material_pickings(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window", "name": _("Material Deliveries"),
            "res_model": "stock.picking", "view_mode": "tree,form",
            "domain": [("id", "in", self.material_picking_ids.ids)],
            "context": {"create": False},
        }


class WorkOrderService(models.Model):
    _inherit = "car.workorder.service"

    materials_issued = fields.Boolean(readonly=True, copy=False)
    material_picking_id = fields.Many2one("stock.picking", readonly=True, copy=False, ondelete="restrict")

    @api.model_create_multi
    def create(self, vals_list):
        if any(vals.get("materials_issued") or vals.get("material_picking_id") for vals in vals_list):
            raise UserError(_("Material issue status is managed by the Finish action."))
        return super().create(vals_list)

    def _get_unlocked_service_fields(self):
        return super()._get_unlocked_service_fields() | {"materials_issued", "material_picking_id"}

    def write(self, vals):
        if {"materials_issued", "material_picking_id"} & vals.keys() and self.env.context.get("material_issue_token") is not _ISSUE_TOKEN:
            raise UserError(_("Material issue status is managed by the Finish action."))
        return super().write(vals)

    def unlink(self):
        for task in self:
            if task.materials_issued:
                raise UserError(_("A service with issued materials cannot be deleted."))
            if task.workorder_id.state == "new":
                task.workorder_id.product_ids.filtered(lambda line: line.source_task_id == task).sudo().unlink()
        return super().unlink()

    def action_finish(self):
        self.ensure_one()
        self.check_access_rights("write")
        self.check_access_rule("write")
        order = self.workorder_id
        order.invalidate_recordset(["state", "product_ids"])
        # Serialize all tasks for an order; ORM stock updates and the issue flag
        # commit together. A repeated finish after QA rework never issues twice.
        self.env.cr.execute("SELECT id FROM car_work_order WHERE id = %s FOR UPDATE", (order.id,))
        order.invalidate_recordset(["state", "product_ids"])
        order.product_ids.invalidate_recordset(["quantity", "lot_id", "source_task_id"])
        order._adopt_existing_materials()
        self.invalidate_recordset(["materials_issued", "state", "material_picking_id"])
        if self.state in ("quality", "done") and self.materials_issued:
            return True
        if order.state != "progress":
            raise UserError(_("Start the work order before finishing a service."))
        with self.env.cr.savepoint():
            result = super().action_finish()
            if not self.materials_issued:
                self._issue_materials()
        return result

    def _issue_materials(self):
        self.ensure_one()
        order = self.workorder_id
        lines = order.product_ids.filtered(lambda line: line.source_task_id == self and line.quantity > 0)
        if not lines:
            self.with_context(material_issue_token=_ISSUE_TOKEN).materials_issued = True
            return
        warehouse = order._get_branch_warehouse()
        company = order.company_id
        location = warehouse.lot_stock_id
        required = {}
        for line in lines:
            product = line.product_id.with_company(company)
            if product.detailed_type != "product":
                raise UserError(_("Material '%s' must be a storable product.") % product.display_name)
            if product.company_id and product.company_id != company:
                raise UserError(_("Materials must belong to the work order's company."))
            if product.tracking != "none" and not line.lot_id:
                raise UserError(_("Select a lot/serial for material '%s' before finishing.") % product.display_name)
            uom = line.used_uom_id or product.uom_id
            qty = uom._compute_quantity(line.quantity, product.uom_id)
            if product.tracking == "serial" and float_compare(qty, 1, precision_rounding=product.uom_id.rounding) != 0:
                raise UserError(_("Each serial-numbered material line must consume exactly one unit."))
            key = (product.id, line.lot_id.id)
            required[key] = required.get(key, 0) + qty
        Quant = self.env["stock.quant"].sudo().with_company(company)
        for (product_id, lot_id), qty in required.items():
            product = self.env["product.product"].browse(product_id)
            lot = self.env["stock.lot"].browse(lot_id)
            if lot:
                quants = Quant._gather(product, location, lot_id=lot).filtered(lambda quant: quant.lot_id == lot)
                available = sum(quants.mapped("quantity")) - sum(quants.mapped("reserved_quantity"))
            else:
                available = Quant._get_available_quantity(product, location)
            if float_compare(available, qty, precision_rounding=product.uom_id.rounding) < 0:
                raise UserError(_("Insufficient available stock for %(product)s: required %(required)s, available %(available)s.",
                                  product=product.display_name, required=qty, available=available))
        picking = self.env["stock.picking"].sudo().with_company(company).create({
            "picking_type_id": warehouse.out_type_id.id,
            "location_id": location.id,
            "location_dest_id": order._get_customer_location(company).id,
            "partner_id": order.partner_id.id,
            "company_id": company.id,
            "origin": "%s / %s" % (order.name, self.product_id.display_name),
            "material_workorder_id": order.id,
            **({"branch_id": order.branch_id.id} if "branch_id" in self.env["stock.picking"]._fields else {}),
        })
        for line in lines:
            move = self.env["stock.move"].sudo().with_company(company).create({
                "name": "%s / %s" % (line.part_id.display_name or self.product_id.display_name, line.product_id.display_name),
                "picking_id": picking.id, "company_id": company.id,
                "product_id": line.product_id.id, "product_uom_qty": line.quantity,
                "product_uom": (line.used_uom_id or line.product_id.uom_id).id,
                "location_id": picking.location_id.id, "location_dest_id": picking.location_dest_id.id,
            })
            # The user has permission to finish the service; inventory is issued
            # through this controlled operation, without broad stock-user access.
            line.sudo().with_context(material_issue_token=_ISSUE_TOKEN).material_move_id = move
        # Keep one stock move per material line, including identical products
        # used on different vehicle parts.
        picking.move_ids._action_confirm(merge=False)
        picking.do_unreserve()
        for line in lines:
            move = line.material_move_id.sudo()
            qty = move.product_uom._compute_quantity(move.product_uom_qty, move.product_id.uom_id)
            move._update_reserved_quantity(qty, location, lot_id=line.lot_id, strict=False)
            if line.lot_id and any(ml.lot_id != line.lot_id for ml in move.move_line_ids):
                raise UserError(_("The selected lot/serial could not be fully reserved. Review its available stock and retry."))
            if float_compare(move.quantity, move.product_uom_qty, precision_rounding=move.product_uom.rounding) != 0:
                raise UserError(_("Stock could not be reserved completely. Review availability and retry."))
            move.picked = True
        picking._action_done()
        self.with_context(material_issue_token=_ISSUE_TOKEN).write({"material_picking_id": picking.id, "materials_issued": True})
        order.message_post(body=_("Service materials issued: %s") % picking.name)


class StockPicking(models.Model):
    _inherit = "stock.picking"

    material_workorder_id = fields.Many2one("car.work.order", readonly=True, copy=False, index=True, ondelete="restrict")
