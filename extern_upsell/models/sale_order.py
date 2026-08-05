from odoo import _, api, fields, models
from odoo.exceptions import UserError


class SaleOrder(models.Model):
    _inherit = "sale.order"

    extern_work_order_id = fields.Many2one(
        "car.work.order",
        string="Extern Work Order",
        compute="_compute_extern_work_order_id",
        help="Main work order of the extern visit. Shared by the extern "
             "order and its extra upsell order.",
    )
    extern_appointment_id = fields.Many2one(
        "car.appointment",
        string="Extern Appointment",
        compute="_compute_extern_appointment_id",
        help="Shared appointment of the extern visit.",
    )
    is_extern_visit_order = fields.Boolean(
        compute="_compute_is_extern_visit_order",
    )

    @api.depends("order_type", "related_sale_id", "related_sale_id.order_type")
    def _compute_is_extern_visit_order(self):
        for order in self:
            order.is_extern_visit_order = bool(order._get_extern_parent_order())

    @api.depends(
        "order_type",
        "related_sale_id",
        "related_sale_id.appointment_ids.car_work_order_id",
        "appointment_ids.car_work_order_id",
    )
    def _compute_extern_work_order_id(self):
        WorkOrder = self.env["car.work.order"]
        for order in self:
            parent = order._get_extern_parent_order()
            if not parent:
                order.extern_work_order_id = False
                continue
            work_order = WorkOrder.search(
                [
                    ("sale_order_id", "=", parent.id),
                    ("parent_id", "=", False),
                ],
                limit=1,
            )
            if not work_order:
                appointment = parent.appointment_ids[:1]
                work_order = (
                    appointment.car_work_order_id if appointment else WorkOrder
                )
            order.extern_work_order_id = work_order

    @api.depends(
        "order_type",
        "related_sale_id",
        "related_sale_id.appointment_ids",
        "appointment_ids",
    )
    def _compute_extern_appointment_id(self):
        for order in self:
            parent = order._get_extern_parent_order()
            order.extern_appointment_id = (
                parent.appointment_ids[:1] if parent else False
            )

    def _get_extern_parent_order(self):
        """Return the extern SO that owns the shared visit."""
        self.ensure_one()
        if self.order_type == "extern":
            return self
        if self.related_sale_id and self.related_sale_id.order_type == "extern":
            return self.related_sale_id
        return self.env["sale.order"]

    def _is_extern_upsell_order(self):
        self.ensure_one()
        return bool(
            self.related_sale_id
            and self.related_sale_id.order_type == "extern"
        )

    def _extern_visit_source_orders(self):
        """Extern SO plus its non-cancelled extra order(s)."""
        self.ensure_one()
        if self.order_type != "extern":
            return self
        return self | self.child_sale_ids.filtered(
            lambda order: order.state != "cancel"
        )

    def _get_extern_appointment_line_defaults(self):
        """Build appointment service/product defaults from extern + extras."""
        self.ensure_one()
        service_products = self.env["product.product"]
        product_lines = []
        seen_product_ids = set()

        for order in self._extern_visit_source_orders():
            for line in order.order_line.filtered(
                lambda sol: not sol.display_type and sol.product_id
            ):
                product = line.product_id
                if product.detailed_type == "service":
                    service_products |= product
                elif product.id not in seen_product_ids:
                    product_lines.append(line)
                    seen_product_ids.add(product.id)

        return service_products, product_lines

    def action_create_appointment(self):
        """Extra upsell orders reuse the extern appointment."""
        for order in self:
            if order._is_extern_upsell_order():
                raise UserError(_(
                    "Extra upsell orders share the extern appointment. "
                    "Open or create the appointment from the extern sale order."
                ))

        self.ensure_one()
        if self.order_type != "extern":
            return super().action_create_appointment()

        appointment = self.env["car.appointment"].search(
            [("sale_order_id", "=", self.id)], limit=1
        )
        if appointment:
            self.child_sale_ids.filtered(
                lambda order: order.state != "cancel"
            )._sync_extern_upsell_to_visit()
            return {
                "type": "ir.actions.act_window",
                "name": _("Appointment"),
                "res_model": "car.appointment",
                "res_id": appointment.id,
                "view_mode": "form",
                "views": [(
                    self.env.ref(
                        "appointment_management.car_appointment_view_form"
                    ).id,
                    "form",
                )],
                "target": "current",
            }

        action = super().action_create_appointment()
        if action.get("res_id"):
            return action

        service_products, product_lines = (
            self._get_extern_appointment_line_defaults()
        )
        context = dict(action.get("context") or {})
        context["default_service_ids"] = [
            (0, 0, {"product_id": product.id})
            for product in service_products
        ]
        context["default_product_ids"] = [
            (0, 0, {
                "product_id": line.product_id.id,
                "quantity": line.product_uom_qty,
            })
            for line in product_lines
        ]
        action["context"] = context
        return action

    def action_view_appointment(self):
        self.ensure_one()
        if self.order_type == "extern":
            self.child_sale_ids.filtered(
                lambda order: order.state != "cancel"
            )._sync_extern_upsell_to_visit()
        elif self._is_extern_upsell_order():
            parent = self._get_extern_parent_order()
            if parent:
                return parent.action_view_appointment()
        return super().action_view_appointment()

    def action_view_child_sale_orders(self):
        self.ensure_one()
        if self.order_type != "extern":
            return super().action_view_child_sale_orders()
        action = self.env["ir.actions.act_window"]._for_xml_id("sale.action_orders")
        action["domain"] = [("related_sale_id", "=", self.id)]
        action["context"] = {
            "default_related_sale_id": self.id,
            "default_partner_id": self.partner_id.id if self.partner_id else False,
            "default_vehicle_id": self.vehicle_id.id if self.vehicle_id else False,
            "default_order_type": "intern",
        }
        if len(self.child_sale_ids) == 1:
            action.update({
                "views": [(False, "form")],
                "res_id": self.child_sale_ids.id,
            })
        return action

    def action_create_extra_sale_order(self):
        """Create Extra SO for Extern (same customer) or fall back to Contract."""
        self.ensure_one()
        if self.order_type == "extern":
            return self._create_extern_extra_sale_order()
        return super().action_create_extra_sale_order()

    def _create_extern_extra_sale_order(self):
        """
        Extra order for the same car owner.
        No agency/salesperson on the extra — commission stays on the parent Extern.
        """
        self.ensure_one()
        if self.state not in ("sale", "done"):
            raise UserError(_(
                "Please confirm the Extern sale order before creating an extra order."
            ))
        if not self.id:
            raise UserError(_("Please save the Extern sale order first."))
        if not self.partner_id:
            raise UserError(_("Please select a customer first."))
        if self.child_sale_ids:
            raise UserError(_(
                "Only one extra sale order is allowed per Extern order."
            ))

        extra = self.env["sale.order"].create({
            "partner_id": self.partner_id.id,
            "related_sale_id": self.id,
            "vehicle_id": self.vehicle_id.id if self.vehicle_id else False,
            "order_type": "intern",
            "origin": self.name,
            "client_order_ref": self.client_order_ref,
            "company_id": self.company_id.id,
            "warehouse_id": self.warehouse_id.id,
            "branch_id": (
                self.branch_id.id
                if "branch_id" in self._fields and self.branch_id
                else False
            ),
            "user_id": self.user_id.id,
            "team_id": self.team_id.id if self.team_id else False,
            "pricelist_id": self.pricelist_id.id if self.pricelist_id else False,
            # Explicitly no agency / referral on the upsell.
            "agency_id": False,
            "agency_salesperson_id": False,
            "commission_amount": 0.0,
            "commission_autochapeau_amount": 0.0,
            "commission_autoflex_amount": 0.0,
        })
        extra.message_post(body=_(
            "Upsell order linked to extern referral %(order)s. "
            "It shares the same appointment/work order and invoices the "
            "car owner. Referral commission applies only to the parent order.",
            order=self.name,
        ))
        return {
            "type": "ir.actions.act_window",
            "name": _("Extra Sale Order"),
            "res_model": "sale.order",
            "res_id": extra.id,
            "view_mode": "form",
            "target": "current",
        }

    def action_confirm(self):
        result = super().action_confirm()
        self.filtered(
            lambda order: order._is_extern_upsell_order()
        )._sync_extern_upsell_to_visit()
        return result

    def write(self, vals):
        result = super().write(vals)
        if "order_line" in vals:
            self.filtered(
                lambda order: order._is_extern_upsell_order()
                and order.state in ("sale", "done")
            )._sync_extern_upsell_to_visit()
        return result

    def _sync_extern_upsell_to_visit(self):
        """Push upsell lines to the shared appointment and work order."""
        self._sync_extern_upsell_to_appointment()
        self._sync_extern_upsell_to_work_order()

    def _sync_extern_upsell_to_appointment(self):
        AppointmentService = self.env["car.appointment.service"]
        AppointmentProduct = self.env["car.appointment.product"]

        for order in self:
            if not order._is_extern_upsell_order() and order.order_type != "extern":
                continue
            appointment = order.extern_appointment_id
            if not appointment or appointment.state == "canceled":
                continue

            source_orders = (
                order._extern_visit_source_orders()
                if order.order_type == "extern"
                else order
            )
            existing_services = appointment.service_ids.mapped("product_id")
            existing_products = appointment.product_ids.mapped("product_id")

            for source in source_orders:
                for line in source.order_line.filtered(
                    lambda sol: not sol.display_type and sol.product_id
                ):
                    product = line.product_id
                    if product.detailed_type == "service":
                        if product in existing_services:
                            continue
                        AppointmentService.create({
                            "appointment_id": appointment.id,
                            "product_id": product.id,
                        })
                        existing_services |= product
                    elif product not in existing_products:
                        AppointmentProduct.create({
                            "appointment_id": appointment.id,
                            "product_id": product.id,
                            "quantity": line.product_uom_qty,
                        })
                        existing_products |= product

    def _sync_extern_upsell_to_work_order(self):
        Service = self.env["car.workorder.service"].with_context(
            extern_upsell_sync=True
        )
        ProductLine = self.env["car.workorder.product"]

        for order in self:
            if not order._is_extern_upsell_order():
                continue
            work_order = order.extern_work_order_id
            if not work_order or work_order.state in ("done", "cancelled"):
                continue

            existing_services = work_order.service_ids.mapped("product_id")
            existing_products = work_order.product_ids.mapped("product_id")

            for line in order.order_line.filtered(
                lambda sol: not sol.display_type and sol.product_id
            ):
                product = line.product_id
                if product.detailed_type == "service":
                    if product in existing_services:
                        continue
                    Service.create({
                        "workorder_id": work_order.id,
                        "product_id": product.id,
                        "expected_duration": product.expected_duration,
                    })
                    existing_services |= product
                    for bom in product.bom_ids:
                        if bom.product_id in existing_products:
                            continue
                        ProductLine.create({
                            "workorder_id": work_order.id,
                            "service_id": bom.service_id.id,
                            "product_id": bom.product_id.id,
                            "quantity": bom.quantity,
                        })
                        existing_products |= bom.product_id
                elif product not in existing_products:
                    ProductLine.create({
                        "workorder_id": work_order.id,
                        "product_id": product.id,
                        "quantity": line.product_uom_qty,
                    })
                    existing_products |= product


class SaleOrderLine(models.Model):
    _inherit = "sale.order.line"

    def _sync_parent_extern_upsell(self):
        orders = self.mapped("order_id").filtered(
            lambda order: order._is_extern_upsell_order()
            and order.state in ("sale", "done")
        )
        orders._sync_extern_upsell_to_visit()

    @api.model_create_multi
    def create(self, vals_list):
        lines = super().create(vals_list)
        lines._sync_parent_extern_upsell()
        return lines

    def write(self, vals):
        result = super().write(vals)
        if any(field in vals for field in ("product_id", "product_uom_qty", "order_id")):
            self._sync_parent_extern_upsell()
        return result
