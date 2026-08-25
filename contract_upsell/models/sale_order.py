from odoo import _, api, fields, models
from odoo.exceptions import UserError


class SaleOrder(models.Model):
    _inherit = "sale.order"

    contract_work_order_id = fields.Many2one(
        "car.work.order",
        string="Contract Work Order",
        compute="_compute_contract_work_order_id",
        help="Main work order of the contract visit. Shared by the contract "
             "order and its extra upsell orders.",
    )
    contract_appointment_id = fields.Many2one(
        "car.appointment",
        string="Contract Appointment",
        compute="_compute_contract_appointment_id",
        help="Shared appointment of the contract visit.",
    )

    @api.depends(
        "order_type",
        "related_sale_id",
        "related_sale_id.appointment_ids.car_work_order_id",
        "appointment_ids.car_work_order_id",
    )
    def _compute_contract_work_order_id(self):
        WorkOrder = self.env["car.work.order"]
        for order in self:
            contract = order._get_contract_parent_order()
            if not contract:
                order.contract_work_order_id = False
                continue
            work_order = WorkOrder.search(
                [
                    ("sale_order_id", "=", contract.id),
                    ("parent_id", "=", False),
                ],
                limit=1,
            )
            if not work_order:
                appointment = contract.appointment_ids[:1]
                work_order = (
                    appointment.car_work_order_id if appointment else WorkOrder
                )
            order.contract_work_order_id = work_order

    @api.depends(
        "order_type",
        "related_sale_id",
        "related_sale_id.appointment_ids",
        "appointment_ids",
    )
    def _compute_contract_appointment_id(self):
        for order in self:
            contract = order._get_contract_parent_order()
            order.contract_appointment_id = (
                contract.appointment_ids[:1] if contract else False
            )

    def _get_contract_parent_order(self):
        """Return the contract SO that owns the shared visit."""
        self.ensure_one()
        if self.order_type == "contract":
            return self
        if self.related_sale_id and self.related_sale_id.order_type == "contract":
            return self.related_sale_id
        return self.env["sale.order"]

    def _is_contract_upsell_order(self):
        self.ensure_one()
        return bool(
            self.related_sale_id
            and self.related_sale_id.order_type == "contract"
        )

    def _contract_visit_source_orders(self):
        """Contract SO plus its non-cancelled extra order(s)."""
        self.ensure_one()
        if self.order_type != "contract":
            return self
        return self | self.child_sale_ids.filtered(
            lambda order: order.state != "cancel"
        )

    def _get_contract_appointment_line_defaults(self):
        """Build appointment service/product defaults from contract + extras."""
        self.ensure_one()
        service_products = self.env["product.product"]
        product_lines = []
        seen_product_ids = set()

        for order in self._contract_visit_source_orders():
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
        """
        Extra upsell orders reuse the contract appointment.
        Contract appointments preload lines from the contract + extra SO.
        """
        for order in self:
            if order._is_contract_upsell_order():
                raise UserError(_(
                    "Extra upsell orders share the contract appointment. "
                    "Open or create the appointment from the contract sale order."
                ))

        self.ensure_one()
        if self.order_type != "contract":
            return super().action_create_appointment()

        appointment = self.env["car.appointment"].search(
            [("sale_order_id", "=", self.id)], limit=1
        )
        if appointment:
            # Keep an existing appointment up to date with both orders.
            self.child_sale_ids.filtered(
                lambda order: order.state != "cancel"
            )._sync_contract_upsell_to_visit()
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
            self._get_contract_appointment_line_defaults()
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
        """Refresh contract appointment lines from both SOs when opening it."""
        self.ensure_one()
        if self.order_type == "contract":
            self.child_sale_ids.filtered(
                lambda order: order.state != "cancel"
            )._sync_contract_upsell_to_visit()
        return super().action_view_appointment()

    def action_create_extra_sale_order(self):
        """Create the extra SO and keep it tied to the contract visit."""
        self.ensure_one()
        if self.state not in ("sale", "done"):
            raise UserError(_(
                "Please confirm the Contract sale order before creating an extra order."
            ))
        action = super().action_create_extra_sale_order()
        # Type/OTP wizards are returned before the Extra Order exists.
        if action.get("res_model") != "sale.order" or not action.get("res_id"):
            return action
        extra = self.env["sale.order"].browse(action.get("res_id"))
        if extra:
            extra.message_post(body=_(
                "Upsell order linked to contract %(contract)s. "
                "It will share the same appointment/work order and invoice "
                "the sub-customer.",
                contract=self.name,
            ))
        return action

    def action_open_split_payment_wizard(self):
        """Contract orders are invoiced to the dealer; no direct collect payment."""
        self.ensure_one()
        if self.order_type == "contract":
            raise UserError(_(
                "Collect Payment is not available on Contract sale orders."
            ))
        return super().action_open_split_payment_wizard()

    def action_sync_contract_upsell_to_visit(self):
        """Manual sync of upsell lines onto the shared appointment and work order."""
        self.ensure_one()
        if self.order_type == "contract":
            orders = self.child_sale_ids.filtered(
                lambda order: order.state in ("sale", "done")
            )
        elif self._is_contract_upsell_order():
            orders = self.filtered(lambda order: order.state in ("sale", "done"))
        else:
            raise UserError(_(
                "Upsell sync is only available on Contract orders and their "
                "extra sale orders."
            ))
        if not orders:
            raise UserError(_("No confirmed extra sale order to sync."))
        orders._sync_contract_upsell_to_visit()
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Upsell Synced"),
                "message": _(
                    "Extra order lines were synced to the contract appointment "
                    "and work order."
                ),
                "type": "success",
                "sticky": False,
            },
        }

    def action_confirm(self):
        result = super().action_confirm()
        self.filtered(
            lambda order: order._is_contract_upsell_order()
        )._sync_contract_upsell_to_visit()
        return result

    def write(self, vals):
        result = super().write(vals)
        if "order_line" in vals:
            self.filtered(
                lambda order: order._is_contract_upsell_order()
                and order.state in ("sale", "done")
            )._sync_contract_upsell_to_visit()
        return result

    def _sync_contract_upsell_to_visit(self):
        """Push upsell lines to the shared appointment and work order."""
        self._sync_contract_upsell_to_appointment()
        self._sync_contract_upsell_to_work_order()

    def _sync_contract_upsell_to_appointment(self):
        """Push upsell SO services/products onto the shared contract appointment."""
        AppointmentService = self.env["car.appointment.service"]
        AppointmentProduct = self.env["car.appointment.product"]

        for order in self:
            if not order._is_contract_upsell_order() and order.order_type != "contract":
                continue
            # Always resolve the shared contract appointment.
            appointment = order.contract_appointment_id
            if not appointment or appointment.state == "canceled":
                continue

            source_orders = (
                order._contract_visit_source_orders()
                if order.order_type == "contract"
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

    def _sync_contract_upsell_to_work_order(self):
        """Push upsell SO services/products onto the shared contract work order."""
        Service = self.env["car.workorder.service"].with_context(
            contract_upsell_sync=True
        )
        ProductLine = self.env["car.workorder.product"]

        for order in self:
            if not order._is_contract_upsell_order():
                continue
            work_order = order.contract_work_order_id
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
                        "workshop_id": product.workshop_id.id,
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

    def _sync_parent_contract_upsell(self):
        orders = self.mapped("order_id").filtered(
            lambda order: order._is_contract_upsell_order()
            and order.state in ("sale", "done")
        )
        orders._sync_contract_upsell_to_visit()

    @api.model_create_multi
    def create(self, vals_list):
        lines = super().create(vals_list)
        lines._sync_parent_contract_upsell()
        return lines

    def write(self, vals):
        result = super().write(vals)
        if any(field in vals for field in ("product_id", "product_uom_qty", "order_id")):
            self._sync_parent_contract_upsell()
        return result
