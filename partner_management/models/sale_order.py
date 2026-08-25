from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.osv import expression


class SaleOrder(models.Model):
    _inherit = "sale.order"

    partner_id = fields.Many2one(
        domain=(
            "[('type', '!=', 'private'), "
            "('company_id', 'in', (False, company_id)), "
            "('contact_partner_type', '=', 'customer')]"
            " + ([('partner_type', '=', 'contract')] if order_type == 'contract' else [])"
        ),
    )

    subordinate_id = fields.Many2one(
        "res.partner",
        string="Car Owner",
        domain="[('partner_type', '=', 'internal')]",
        help="Internal customer served under this Contract order.",
    )
    subordinate_mobile = fields.Char(
        related="subordinate_id.mobile",
        string="Mobile",
        readonly=False,
    )
    subordinate_email = fields.Char(
        related="subordinate_id.email",
        string="Email",
        readonly=False,
    )
    vehicle_id = fields.Many2one(
        "fleet.vehicle",
        string="Car",
        readonly=False,
        domain=(
            "[('partner_id', '=', "
            "subordinate_id if order_type == 'contract' else partner_id)]"
        ),
    )
    vehicle_size = fields.Selection(
        related="vehicle_id.size",
        string="Car Size",
    )

    related_sale_id = fields.Many2one(
        "sale.order",
        string="Related Sale Order",
        index=True,
        copy=False,
        help="Parent contract order this extra order is linked to. "
             "Each order keeps its own invoice partner.",
    )
    child_sale_ids = fields.One2many(
        "sale.order",
        "related_sale_id",
        string="Extra Orders",
        copy=False,
    )
    child_sale_count = fields.Integer(
        string="Extra Orders Count",
        compute="_compute_child_sale_count",
    )
    appointment_ids = fields.One2many(
        "car.appointment",
        "sale_order_id",
        string="Appointments",
    )
    appointment_count = fields.Integer(
        string="Appointment Count",
        compute="_compute_appointment_count",
    )
    has_booking_for_payment = fields.Boolean(
        string="Has Booking For Payment",
        compute="_compute_has_booking_for_payment",
        help="True when this order or its related parent order has an appointment.",
    )
    has_storable_product_lines = fields.Boolean(
        string="Has Storable Lines",
        compute="_compute_product_line_type_flags",
    )
    has_service_product_lines = fields.Boolean(
        string="Has Service Lines",
        compute="_compute_product_line_type_flags",
    )

    def _get_vehicle_size_product_domain(self):
        """Show products without Size, or products matching the car size."""
        self.ensure_one()
        size = self.vehicle_id.size if self.vehicle_id else False
        return self.env["product.product"]._vehicle_size_domain(size)

    def _get_product_catalog_domain(self):
        domain = super()._get_product_catalog_domain()
        size_domain = self._get_vehicle_size_product_domain()
        if size_domain:
            domain = expression.AND([domain, size_domain])
        return domain

    def _get_action_add_from_catalog_extra_context(self):
        ctx = super()._get_action_add_from_catalog_extra_context()
        size = self.vehicle_id.size if self.vehicle_id else False
        if size:
            ctx = dict(ctx, vehicle_size_filter=size)
        return ctx

    @api.depends("child_sale_ids")
    def _compute_child_sale_count(self):
        for order in self:
            order.child_sale_count = len(order.child_sale_ids)

    @api.depends("appointment_ids")
    def _compute_appointment_count(self):
        for order in self:
            order.appointment_count = len(order.appointment_ids)

    @api.depends(
        "appointment_ids",
        "related_sale_id",
        "related_sale_id.appointment_ids",
    )
    def _compute_has_booking_for_payment(self):
        """Extras share the parent contract/extern appointment."""
        for order in self:
            order.has_booking_for_payment = bool(
                order.appointment_ids
                or order.related_sale_id.appointment_ids
            )

    @api.depends(
        "order_line.product_id",
        "order_line.product_id.type",
        "order_line.display_type",
    )
    def _compute_product_line_type_flags(self):
        for order in self:
            lines = order.order_line.filtered(
                lambda line: not line.display_type and line.product_id
            )
            types = set(lines.mapped("product_id.type"))
            order.has_storable_product_lines = "product" in types
            order.has_service_product_lines = "service" in types

    @api.constrains("related_sale_id")
    def _check_related_sale_id(self):
        for order in self:
            if not order.related_sale_id:
                continue
            if order.related_sale_id == order:
                raise ValidationError(_(
                    "A sale order cannot be linked to itself."
                ))
            if order.related_sale_id.related_sale_id:
                raise ValidationError(_(
                    "Only one level of related sale orders is allowed. "
                    "Link extras directly to the contract order."
                ))

    def write(self, vals):
        if "pricelist_id" in vals:
            new_pricelist_id = vals.get("pricelist_id") or False
            if isinstance(new_pricelist_id, models.BaseModel):
                new_pricelist_id = new_pricelist_id.id
            for order in self.filtered("related_sale_id"):
                current_id = order.pricelist_id.id if order.pricelist_id else False
                if new_pricelist_id != current_id:
                    raise UserError(_(
                        "You cannot change the pricelist on a sub sale order."
                    ))
        return super().write(vals)

    @api.onchange("partner_id")
    def _onchange_partner_id_reset_vehicle(self):
        self._reset_vehicle_if_invalid()

    @api.onchange("order_type")
    def _onchange_order_type_reset_vehicle(self):
        if self.order_type != "contract":
            self.subordinate_id = False
        self._reset_vehicle_if_invalid()

    @api.onchange("subordinate_id")
    def _onchange_subordinate_id_reset_vehicle(self):
        self._reset_vehicle_if_invalid()

    def _vehicle_owner_partner(self):
        self.ensure_one()
        if self.order_type == "contract":
            return self.subordinate_id
        return self.partner_id

    def _unverified_intern_extern_orders(self):
        return self.filtered(
            lambda order: order.order_type in ("intern", "extern")
            and order.partner_id
            and not order.partner_id.mobile_verified
        )

    def _action_open_confirm_otp_wizard(self):
        self.ensure_one()
        partner = self.partner_id
        return {
            "type": "ir.actions.act_window",
            "name": _("Verify Customer Mobile"),
            "res_model": "sale.order.confirm.otp.wizard",
            "view_mode": "form",
            "views": [(False, "form")],
            "target": "new",
            "context": {
                "default_sale_order_id": self.id,
                "default_partner_id": partner.id,
                "default_mobile": partner.mobile,
                "default_country_id": partner.country_id.id,
            },
        }

    def action_confirm(self):
        if self.env.context.get("skip_confirm_otp_wizard"):
            return super().action_confirm()
        unverified = self._unverified_intern_extern_orders()
        if not unverified:
            return super().action_confirm()
        if len(self) == 1:
            return self._action_open_confirm_otp_wizard()
        raise UserError(_(
            "Cannot confirm Intern/Extern orders until each customer's "
            "mobile number is verified via OTP."
        ))

    def _reset_vehicle_if_invalid(self):
        owner = self._vehicle_owner_partner()
        if self.vehicle_id and self.vehicle_id.partner_id != owner:
            self.vehicle_id = False

    def action_create_appointment(self):
        """Open an appointment linked to this order, without creating duplicates."""
        self.ensure_one()
        if not self.id:
            raise UserError(_("Please save the sale order first."))
        if not self.vehicle_id:
            raise UserError(_("Please select a car before creating an appointment."))
        if not self.has_service_product_lines:
            raise UserError(_(
                "Create Appointment is only available when the order has at least "
                "one service product line."
            ))

        appointment = self.env["car.appointment"].search(
            [("sale_order_id", "=", self.id)], limit=1
        )
        if appointment:
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

        customer = (
            self.subordinate_id
            if self.order_type == "contract" and self.subordinate_id
            else self.partner_id
        )
        if not customer:
            raise UserError(_("Please select a customer first."))

        service_products = self.order_line.mapped("product_id").filtered(
            lambda product: product.detailed_type == "service"
        )
        product_lines = self.order_line.filtered(
            lambda line: line.product_id
            and line.product_id.detailed_type != "service"
        )
        return {
            "type": "ir.actions.act_window",
            "name": _("Create Appointment"),
            "res_model": "car.appointment",
            "view_mode": "form",
            "views": [(
                self.env.ref(
                    "appointment_management.car_appointment_view_form"
                ).id,
                "form",
            )],
            "target": "current",
            "context": {
                "default_partner_id": customer.id,
                "default_vehicle_id": self.vehicle_id.id,
                "default_sale_order_id": self.id,
                "default_company_id": self.company_id.id,
                "default_branch_id": (
                    self.branch_id.id
                    if "branch_id" in self._fields and self.branch_id
                    else False
                ),
                "default_service_ids": [
                    (0, 0, {"product_id": product.id})
                    for product in service_products
                ],
                "default_product_ids": [
                    (0, 0, {
                        "product_id": line.product_id.id,
                        "quantity": line.product_uom_qty,
                    })
                    for line in product_lines
                ],
            },
        }

    def action_view_appointment(self):
        """Open the single appointment linked to this sale order."""
        self.ensure_one()
        appointment = self.appointment_ids[:1]
        if not appointment:
            raise UserError(_("No appointment is linked to this sale order."))
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

    def action_open_split_payment_wizard(self):
        """Collect Payment requires service lines and an existing appointment."""
        self.ensure_one()
        if not self.has_service_product_lines:
            raise UserError(_(
                "Collect Payment is only available when the order has at least "
                "one service product line."
            ))
        if not self.has_booking_for_payment:
            raise UserError(_(
                "Collect Payment is not available until an appointment/booking "
                "exists for this sale order."
            ))
        return super().action_open_split_payment_wizard()

    def action_view_child_sale_orders(self):
        self.ensure_one()
        action = self.env["ir.actions.act_window"]._for_xml_id("sale.action_orders")
        action["domain"] = [("related_sale_id", "=", self.id)]
        action["context"] = {
            "default_related_sale_id": self.id,
            "default_partner_id": (
                self.subordinate_id.id if self.subordinate_id else False
            ),
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
        """Create Extra Order: type wizard → OTP (if needed) → create."""
        self.ensure_one()
        self._check_extra_sale_order_ready()
        if not self.env.context.get("skip_extra_order_type_wizard"):
            return self._action_open_extra_order_type_wizard()

        order_type = self.env.context.get("extra_order_type") or "intern"
        if not self.subordinate_id.mobile_verified:
            if not self.subordinate_id.mobile:
                raise UserError(_(
                    "Please set a mobile number on the Sub-customer before "
                    "creating an Extra Order."
                ))
            return self._action_open_subordinate_otp_wizard(
                extra_order_type=order_type
            )
        return self._create_extra_sale_order_action(order_type=order_type)

    def _check_extra_sale_order_ready(self):
        self.ensure_one()
        if self.order_type != "contract":
            raise UserError(_(
                "Extra orders can only be created from a Contract sale order."
            ))
        if not self.subordinate_id:
            raise UserError(_(
                "Please select a Sub-customer before creating an extra order."
            ))
        if not self.id:
            raise UserError(_(
                "Please save the contract sale order first."
            ))

    def _action_open_extra_order_type_wizard(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Create Extra Order"),
            "res_model": "sale.extra.order.type.wizard",
            "view_mode": "form",
            "views": [(False, "form")],
            "target": "new",
            "context": {
                "default_sale_order_id": self.id,
                "default_order_type": "intern",
            },
        }

    def _action_open_subordinate_otp_wizard(self, extra_order_type="intern"):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Verify Sub-customer Mobile"),
            "res_model": "sale.extra.order.otp.wizard",
            "view_mode": "form",
            "views": [(False, "form")],
            "target": "new",
            "context": {
                "default_sale_order_id": self.id,
                "default_partner_id": self.subordinate_id.id,
                "default_mobile": self.subordinate_id.mobile,
                "default_country_id": (
                    self.subordinate_id.country_id.id
                    or self.partner_id.country_id.id
                ),
                "default_extra_order_type": extra_order_type or "intern",
            },
        }

    def _create_extra_sale_order_action(self, order_type="intern"):
        self.ensure_one()
        self._check_extra_sale_order_ready()
        if order_type not in ("intern", "extern"):
            raise UserError(_("Invalid Extra Order type."))
        vals = {
            "partner_id": self.subordinate_id.id,
            "related_sale_id": self.id,
            "vehicle_id": self.vehicle_id.id if self.vehicle_id else False,
            "order_type": order_type,
            "origin": self.name,
            "client_order_ref": self.client_order_ref,
            "company_id": self.company_id.id,
            "warehouse_id": self.warehouse_id.id,
            "branch_id": self.branch_id.id if "branch_id" in self._fields and self.branch_id else False,
            "user_id": self.user_id.id,
            "team_id": self.team_id.id if self.team_id else False,
        }
        if order_type != "extern":
            # Keep extras clean unless explicitly Extern.
            vals.update({
                "agency_id": False,
                "agency_salesperson_id": False,
            })
        extra = self.env["sale.order"].create(vals)
        return {
            "type": "ir.actions.act_window",
            "name": _("Extra Sale Order"),
            "res_model": "sale.order",
            "res_id": extra.id,
            "view_mode": "form",
            "target": "current",
        }


class SaleOrderLine(models.Model):
    _inherit = "sale.order.line"

    def _get_size_attribute_values(self):
        """Size values selected on the line (variant and no_variant attributes)."""
        self.ensure_one()
        size_attributes = self.env["product.template"]._vehicle_size_attributes()
        if not size_attributes:
            return self.env["product.template.attribute.value"]
        ptavs = (
            self.product_id.product_template_attribute_value_ids
            | self.product_no_variant_attribute_value_ids
        )
        return ptavs.filtered(lambda ptav: ptav.attribute_id in size_attributes)

    @api.constrains(
        "product_id", "product_no_variant_attribute_value_ids", "order_id"
    )
    def _check_product_matches_vehicle_size(self):
        for line in self:
            size = line.order_id.vehicle_id.size
            if not size or not line.product_id:
                continue
            size_values = line._get_size_attribute_values()
            if not size_values:
                continue
            codes = size_values.product_attribute_value_id.mapped("code")
            if size not in codes:
                raise ValidationError(_(
                    "The product \"%(product)s\" does not match the size of the "
                    "car \"%(car)s\". Please pick a product of the same size.",
                    product=line.product_id.display_name,
                    car=line.order_id.vehicle_id.display_name,
                ))

    @api.constrains("product_uom_qty", "product_id")
    def _check_single_quantity(self):
        for line in self:
            if line.display_type or not line.product_id:
                continue
            if (
                line.product_id.detailed_type == "service"
                and line.product_uom_qty > 1
            ):
                raise ValidationError(_(
                    "Service products cannot have a quantity greater than 1."
                ))
            if line.order_id.vehicle_id and line.product_uom_qty > 1:
                raise ValidationError(_(
                    "Only one unit per line is allowed on a car sale order."
                ))
