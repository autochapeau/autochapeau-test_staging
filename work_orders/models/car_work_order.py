import logging
import time
import functools
from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.fields import Command


def retry_on_serialization_failure(max_tries=5, delay=0.1, backoff=2.0):
    def decorator(func):
        @functools.wraps(func)
        def wrapper(self, *args, **kwargs):
            _delay = delay
            for attempt in range(1, max_tries + 1):
                try:
                    return func(self, *args, **kwargs)
                except Exception as e:
                    # Detect PostgreSQL serialization failure (SQLSTATE 40001)
                    pgcode = getattr(e, 'pgcode', None)
                    orig_pgcode = getattr(
                        getattr(e, 'orig', None), 'pgcode', None)
                    msg = str(e).lower()
                    is_serial = (
                        pgcode == '40001' or orig_pgcode == '40001' or
                        'could not serialize' in msg or 'mise à jour en parallèle' in msg
                    )
                    if not is_serial or attempt == max_tries:
                        raise
                    time.sleep(_delay)
                    _delay *= backoff
            return func(self, *args, **kwargs)
        return wrapper
    return decorator


class CarWorkcenter(models.Model):
    _name = "car.workcenter"
    _description = "Work center"

    name = fields.Char(required=True)
    code = fields.Char(copy=False)
    employee_ids = fields.Many2many("hr.employee", string="Employees")
    company_id = fields.Many2one(
        "res.company", string="Company", default=lambda self: self.env.company, required=True)
    branch_id = fields.Many2one(
        "hr.department",
        string="Branch",
        domain="[('department_type', '=', 'branche')]",
        help="Branch related to the employee",
    )


class CarWorkshop(models.Model):
    _name = "car.workshop"
    _description = "Workshop"

    name = fields.Char(required=True)
    company_id = fields.Many2one(
        "res.company", string="Company", default=lambda self: self.env.company, required=True)
    staff_ids = fields.Many2many(
        'hr.employee', 'car_workshop_staff_rel', 'workshop_id', 'employee_id',
        string='Staff', help='Staff members for this workshop')

    branch_id = fields.Many2one(
        "hr.department",
        string="Branch",
        domain="[('department_type', '=', 'branche')]",
        help="Branch related to the employee",
    )


class CarWorkOrder(models.Model):
    _name = "car.work.order"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _description = "Car Work Order"
    _order = "id desc"
    refuse_reason = fields.Text(
        string="Refusal Reason", readonly=True, copy=False)

    @api.model
    def _partner_ids_by_phone_term(self, term):
        normalized = "".join(ch for ch in (term or "") if ch.isdigit())
        if not normalized:
            return []
        like_term = f"%{normalized}%"
        self.env.cr.execute(
            """
                SELECT id
                  FROM res_partner
                 WHERE regexp_replace(COALESCE(phone, ''), '\\D', '', 'g') LIKE %s
                    OR regexp_replace(COALESCE(mobile, ''), '\\D', '', 'g') LIKE %s
            """,
            [like_term, like_term],
        )
        return [row[0] for row in self.env.cr.fetchall()]

    @api.depends("partner_id.phone", "partner_id.mobile")
    def _compute_partner_phone_search(self):
        for rec in self:
            phone = rec.partner_id.phone or ""
            mobile = rec.partner_id.mobile or ""
            rec.partner_phone_search = " ".join(
                [
                    "".join(ch for ch in phone if ch.isdigit()),
                    "".join(ch for ch in mobile if ch.isdigit()),
                ]
            ).strip()

    @api.model
    def _search_partner_phone_search(self, operator, value):
        if operator not in ("ilike", "like", "=", "=ilike", "=like"):
            return [("id", "=", 0)]
        partner_ids = self._partner_ids_by_phone_term(value)
        if not partner_ids:
            return [("id", "=", 0)]
        return [("partner_id", "in", partner_ids)]

    @api.model
    def _name_search(self, name="", args=None, operator="ilike", limit=100, order=None):
        args = list(args or [])
        result_ids = super()._name_search(name=name, args=args,
                                          operator=operator, limit=limit, order=order)
        if not name or (limit and len(result_ids) >= limit):
            return result_ids

        partner_ids = self._partner_ids_by_phone_term(name)
        if not partner_ids:
            return result_ids

        remaining = False if not limit else max(limit - len(result_ids), 0)
        extra_args = args + [("id", "not in", result_ids),
                             ("partner_id", "in", partner_ids)]
        extra_ids = list(self._search(
            extra_args, limit=remaining, order=order))
        return result_ids + extra_ids

    branch_id = fields.Many2one(
        'hr.department',
        string='Branch',
        domain="[('department_type', '=', 'branche')]",
        readonly=True,
        help="Branch selected in check-in."
    )
    qa_check_item_ids = fields.One2many(
        'workorder.qa.check.item', 'workorder_id', string='QA Check List', copy=False)

    def action_view_invoices(self):
        """
        Pour un sub order, affiche la liste des factures de tous les sale orders des sub orders du même parent (list view).
        Pour un work order principal, affiche les factures liées à son sale order.
        """
        self.ensure_one()
        # If sub order (parent_id exists), retrieve all sale orders from the sub orders of the same parent
        if self.parent_id:
            siblings = self.parent_id.child_ids
            sale_orders = siblings.mapped('sale_order_id')
            invoices = self.env['account.move'].search([
                ('invoice_origin', 'in', sale_orders.mapped('name')),
                ('move_type', 'in', ['out_invoice', 'out_refund'])
            ])
        else:
            sale_order = self.sale_order_id
            if not sale_order:
                raise UserError(
                    _("Aucune sale order n'est liée à cet ordre de travail."))
            invoices = self.env['account.move'].search([
                ('invoice_origin', '=', sale_order.name),
                ('move_type', 'in', ['out_invoice', 'out_refund'])
            ])
        action = self.env.ref('account.action_move_out_invoice_type').read()[0]
        action['views'] = [(False, 'list'), (False, 'form')]
        if invoices:
            action['domain'] = [('id', 'in', invoices.ids)]
        else:
            action['domain'] = [('id', '=', 0)]
        action.pop('res_id', None)
        return action

    sale_order_id = fields.Many2one(
        "sale.order", string="Sale Order", readonly=True)

    def action_view_sale_order(self):
        self.ensure_one()
        if not self.sale_order_id:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Aucune commande liée'),
                    'message': _('Aucune sale order n\'est liée à cet ordre de travail.'),
                    'sticky': False,
                    'type': 'warning',
                }
            }
        action = self.env.ref("sale.action_orders").read()[0]
        action["views"] = [(False, "form")]
        action["res_id"] = self.sale_order_id.id
        return action

    def action_create_invoice(self):
        """Ouvre l'assistant de facturation pour la sale order liée au work order."""
        self.ensure_one()
        sale_order = self.sale_order_id
        if not sale_order:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Aucune commande liée'),
                    'message': _('Aucune sale order n\'est liée à cet ordre de travail.'),
                    'sticky': False,
                    'type': 'warning',
                }
            }
        action = self.env["ir.actions.actions"]._for_xml_id(
            "sale.action_view_sale_advance_payment_inv")
        action["context"] = {"active_ids": [
            sale_order.id], "active_model": "sale.order"}
        return action

    def action_create_sub_order(self):
        self.ensure_one()
        # Count the existing sub-orders for this parent
        sub_orders_count = self.env["car.work.order"].search_count([
            ("parent_id", "=", self.id)
        ])
        next_num = sub_orders_count + 1

        # Use the parent's name as a base
        base_name = self.name or "WO/"
        sub_name = f"{base_name}-{next_num:05d}"

        vals = self.copy_data()[0]
        vals["name"] = sub_name
        vals["state"] = "new"
        vals["parent_id"] = self.id
        vals["car_checkout_id"] = False
        vals["picking_id"] = False
        vals["appointment_id"] = False
        vals["car_checkin_id"] = False
        vals["notes"] = False
        # Do not copy services and products to avoid stock conflicts
        vals["service_ids"] = False
        vals["product_ids"] = False

        # The creation of the sale order is now handled only in the create method

        new_order = self.create(vals)
        _logger = logging.getLogger(__name__)
        _logger.info("[DEBUG] Création sub order %s, sale_order_id=%s", new_order.id,
                     new_order.sale_order_id.id if new_order.sale_order_id else None)
        action = self.env.ref("work_orders.car_work_order_action")
        action = action.read()[0] if action else {}
        action["views"] = [(False, "form")]
        action["res_id"] = new_order.id
        return action

    active = fields.Boolean(default=True)
    name = fields.Char(string="Ref.", readonly=True, copy=False)
    parent_id = fields.Many2one(
        "car.work.order", string="Parent Work Order", readonly=True)
    child_ids = fields.One2many(
        "car.work.order", "parent_id", string="Sub Orders")
    company_id = fields.Many2one(
        "res.company", string="Agency", default=lambda self: self.env.company, required=True)
    appointment_id = fields.Many2one("car.appointment")
    date_appointment = fields.Datetime(
        related="appointment_id.start_date", store=True, readonly=True)
    car_checkin_id = fields.Many2one(
        related="appointment_id.car_checkin_id", readonly=True)
    date_checkin = fields.Datetime(
        related="car_checkin_id.date", store=True, readonly=True)
    checkin_state = fields.Selection(
        related="car_checkin_id.state", string="Check-in Status", readonly=True)
    car_checkout_id = fields.Many2one("car.checkout", readonly=True)
    attachment_ids = fields.Many2many("ir.attachment", string="Attachments")
    notes = fields.Text()
    state = fields.Selection(
        [
            ("new", "New"),
            ("confirmed", "Confirmed"),
            ("progress", "Progress"),
            ("quality", "Quality check"),
            ("quality_confirmed", "Quality confirmed"),
            ("done", "Done"),
            ("cancelled", "Cancelled"),
        ],
        default="new",
        tracking=True,
    )

    vehicle_id = fields.Many2one("fleet.vehicle", required=True, readonly=True)
    vehicle_license_plate = fields.Char(related="vehicle_id.license_plate")
    vehicle_vin_sn = fields.Char(related="vehicle_id.vin_sn")
    vehicle_color_id = fields.Many2one(related="vehicle_id.vehicle_color_id")
    vehicle_size = fields.Selection(related="vehicle_id.size")
    partner_id = fields.Many2one(
        "res.partner", "Customer", required=True, readonly=True)
    partner_phone = fields.Char(related="partner_id.phone")
    partner_phone_search = fields.Char(
        string="Phone Search",
        compute="_compute_partner_phone_search",
        search="_search_partner_phone_search",
    )
    partner_email = fields.Char(related="partner_id.email")
    service_ids = fields.One2many(
        "car.workorder.service", "workorder_id", "Services")
    product_ids = fields.One2many(
        "car.workorder.product", "workorder_id", "Products")
    picking_id = fields.Many2one(
        "stock.picking", "Stock Transfert", readonly=True)

    @api.onchange('appointment_id')
    def _onchange_appointment_set_sale_order(self):
        for rec in self:
            if rec.appointment_id and rec.appointment_id.sale_order_id:
                rec.sale_order_id = rec.appointment_id.sale_order_id.id
            else:
                # do not overwrite an explicitly set sale_order_id for sub-orders
                if not rec.parent_id:
                    rec.sale_order_id = False

    def write(self, vals):
        res = super().write(vals)
        # Handle appointment change propagation
        if 'appointment_id' in vals:
            for rec in self:
                if rec.appointment_id and rec.appointment_id.sale_order_id:
                    # ensure stored value reflects appointment
                    super(CarWorkOrder, rec).write(
                        {'sale_order_id': rec.appointment_id.sale_order_id.id})
                    # propagate to linked checkout if exists
                    if rec.car_checkout_id:
                        rec.car_checkout_id.sudo().write(
                            {'sale_order_id': rec.sale_order_id.id if rec.sale_order_id else False})
                else:
                    if not rec.parent_id:
                        super(CarWorkOrder, rec).write(
                            {'sale_order_id': False})
                        if rec.car_checkout_id:
                            rec.car_checkout_id.sudo().write(
                                {'sale_order_id': False})
        # If sale_order_id changed, propagate to linked checkout
        if 'sale_order_id' in vals:
            for rec in self:
                if rec.car_checkout_id:
                    rec.car_checkout_id.sudo().write(
                        {'sale_order_id': rec.sale_order_id.id if rec.sale_order_id else False})
        return res

    def create(self, vals):
        # Always propagate branch from checkin for main work order
        if not vals.get("parent_id"):
            name = self.env["ir.sequence"].next_by_code("car.work.order.seq")
            vals.update({"name": name})
            # If not set, get from checkin (even if not in vals)
            checkin_id = vals.get('car_checkin_id')
            if not vals.get('branch_id') and checkin_id:
                checkin = self.env['car.checkin'].browse(checkin_id)
                if checkin.branch_id:
                    vals['branch_id'] = checkin.branch_id.id
            rec = super().create(vals)
            # If still not set, try to get from related checkin (for manual creations)
            if not rec.branch_id and rec.car_checkin_id and rec.car_checkin_id.branch_id:
                rec.branch_id = rec.car_checkin_id.branch_id.id
            if rec.appointment_id and not rec.sale_order_id and rec.appointment_id.sale_order_id:
                rec.sale_order_id = rec.appointment_id.sale_order_id.id
            return rec

        # For sub order, always propagate branch from parent
        parent = self.browse(vals["parent_id"]) if vals.get(
            "parent_id") else False
        sale_order_id = False
        if parent and parent.appointment_id and parent.appointment_id.sale_order_id:
            parent_sale = parent.appointment_id.sale_order_id
            sub_orders_count = self.env["car.work.order"].search_count([
                ("parent_id", "=", parent.id)
            ])
            next_num = sub_orders_count + 1
            base_so_name = parent_sale.name
            sub_so_name = f"{base_so_name}-{next_num:05d}"
            # Propagate the branch and analytic account from the parent
            branch_id = parent.branch_id.id if parent.branch_id else False
            analytic_account_id = parent.branch_id.analytic_account_id.id if parent.branch_id and parent.branch_id.analytic_account_id else False
            sale_order_vals = {
                "name": sub_so_name,
                "partner_id": parent_sale.partner_id.id,
                "vehicle_id": parent_sale.vehicle_id.id if hasattr(parent_sale, "vehicle_id") else False,
                "appointment_slot_id": parent_sale.appointment_slot_id.id if hasattr(parent_sale, "appointment_slot_id") else False,
                "branch_id": branch_id,
                "analytic_account_id": analytic_account_id,
            }
            sale_order = self.env["sale.order"].create(sale_order_vals)
            sale_order_id = sale_order.id
        # Always propagate branch from parent
        if parent and parent.branch_id:
            vals['branch_id'] = parent.branch_id.id
        if sale_order_id:
            vals["appointment_id"] = False
            vals["sale_order_id"] = sale_order_id
        rec = super().create(vals)
        # If still not set, try to get from parent (for manual creations)
        if not rec.branch_id and rec.parent_id and rec.parent_id.branch_id:
            rec.branch_id = rec.parent_id.branch_id.id
        return rec
        # Always propagate branch from parent for sub order
        if not vals.get('branch_id') and parent and parent.branch_id:
            vals['branch_id'] = parent.branch_id.id
        if sale_order_id:
            vals["appointment_id"] = False
            vals["sale_order_id"] = sale_order_id
        rec = super().create(vals)
        return rec

    def action_confirm(self):
        self.ensure_one()
        if self.checkin_state != "done":
            raise UserError(
                _("Check-in must be completed (status 'Done') before you can confirm this work order."))
        # Service and staff check
        if not self.service_ids:
            raise UserError(
                _("You must add at least one service before confirming the work order."))
        has_staff = any(service.staff_ids for service in self.service_ids)
        if not has_staff:
            raise UserError(
                _("You must select at least one staff on a service before confirming the work order."))
        picking_type_internal = self.env.ref("stock.picking_type_internal")
        location_id = picking_type_internal.default_location_src_id.id
        location_dest_id = picking_type_internal.default_location_dest_id.id
        picking_vals = {
            "picking_type_id": picking_type_internal.id,
            "location_id": location_id,
            "location_dest_id": location_dest_id,
            "origin": self.appointment_id.sale_order_id.name if self.appointment_id.sale_order_id else "",
            "move_ids": [
                Command.create(
                    {
                        "product_id": line.product_id.id,
                        "product_uom_qty": line.quantity,
                        "location_id": location_id,
                        "location_dest_id": location_dest_id,
                        "name": line.product_id.name,
                    }
                )
                for line in self.product_ids
            ],
        }
        # branch_id can come from optional branch modules, so only set it when available.
        if "branch_id" in self.env["stock.picking"]._fields:
            picking_vals["branch_id"] = self.branch_id.id if self.branch_id else False

        picking = self.env["stock.picking"].create(picking_vals)
        self.picking_id = picking
        self.state = "confirmed"

    def action_progress(self):
        self.ensure_one()
        self.state = "progress"

    def action_quality(self):
        self.ensure_one()
        # Ensure QA checklist lines exist (copy from related checkin of same sale order)
        self._ensure_qa_check_items()
        self.state = "quality"

    def _get_source_checkin(self):
        """Return the relevant `car.checkin` to copy items from.
        Prefer the related `car_checkin_id`, otherwise the latest checkin for the same sale order.
        """
        self.ensure_one()
        # prefer explicit related checkin
        if self.car_checkin_id:
            return self.car_checkin_id
        # fallback: latest checkin for the same sale order
        sale = self.sale_order_id or (
            self.appointment_id.sale_order_id if self.appointment_id and self.appointment_id.sale_order_id else False)
        if sale:
            checkin = self.env['car.checkin'].search(
                [('sale_order_id', '=', sale.id)], order='id desc', limit=1)
            return checkin or False
        return False

    def _ensure_qa_check_items(self):
        for rec in self:
            # don't duplicate if already present
            if rec.qa_check_item_ids:
                continue
            checkin = rec._get_source_checkin()
            # prefer explicit items from the checkin; fallback to global car.check.item masters
            source_items = []
            if checkin and getattr(checkin, 'car_check_item_ids', False):
                source_items = [
                    ln.car_check_item_id for ln in checkin.car_check_item_ids if ln.car_check_item_id]
            if not source_items:
                source_items = self.env['car.check.item'].search([])

            for car_item in source_items:
                if not car_item:
                    continue
                # find or create corresponding qa.check.item by name
                qa_item = self.env['qa.check.item'].search(
                    [('name', '=', car_item.name)], limit=1)
                if not qa_item:
                    qa_item = self.env['qa.check.item'].create(
                        {'name': car_item.name})
                # avoid duplicate workorder lines
                exists = self.env['workorder.qa.check.item'].search([
                    ('workorder_id', '=', rec.id), ('qa_check_item_id', '=', qa_item.id)
                ], limit=1)
                if not exists:
                    # preserve checked state when available (from checkin), otherwise default False
                    checked_val = False
                    if checkin and getattr(checkin, 'car_check_item_ids', False):
                        for ln in checkin.car_check_item_ids:
                            if ln.car_check_item_id == car_item:
                                checked_val = bool(
                                    getattr(ln, 'checked', False))
                                break
                    self.env['workorder.qa.check.item'].create({
                        'qa_check_item_id': qa_item.id,
                        'checked': checked_val,
                        'workorder_id': rec.id,
                    })

    def action_confirm_quality(self):
        self.ensure_one()
        self.state = "quality_confirmed"

    def action_refuse_quality(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'quality.refuse.reason.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_reason': '', 'active_id': self.id},
        }

    @retry_on_serialization_failure(max_tries=5, delay=0.05, backoff=2.0)
    def action_done(self):
        self.ensure_one()
        # Lock this work order row to prevent concurrent updates that
        # can cause PostgreSQL serialization failures when multiple
        # clients try to mark done at the same time.
        self.env.cr.execute(
            "SELECT id FROM car_work_order WHERE id = %s FOR UPDATE", (self.id,))
        self_vals = {"state": "done"}
        # Create a car checkout
        if not self.car_checkout_id:
            # include sale order id if available
            sale_id = self.sale_order_id.id if self.sale_order_id else (
                self.appointment_id.sale_order_id.id if self.appointment_id and self.appointment_id.sale_order_id else False)
            checkout_vals = {
                "car_work_order_id": self.id,
                "partner_id": self.partner_id.id,
                "vehicle_id": self.vehicle_id.id,
                "company_id": self.company_id.id,
                "sale_order_id": sale_id,
            }
            car_checkout = self.env["car.checkout"].sudo().create(
                checkout_vals)
            self_vals["car_checkout_id"] = car_checkout.id
        self.write(self_vals)
        # Compose and send SMS
        phone = self.partner_id.mobile or self.partner_id.phone
        country_code = self.partner_id.country_id.phone_code if self.partner_id.country_id else ""
        if phone and not phone.startswith("+") and country_code:
            phone = f"+{country_code}{phone}"
        if phone:
            # flake8: noqa: UP031
            message_text_en = (
                "Dear Customer,\n\n"
                "Your Order [%(order_name)s] has been completed on your car [%(plate)s].\n\n"
                "You can now pick up your car.\n\n"
                "Thank you for your trust!"
            ) % {
                "order_name": self.name or "",
                "plate": self.vehicle_license_plate or "",
            }
            message_text_ar = (
                "عميلنا العزيز،\n\n"
                "تم الإنتهاء من تنفيذ طلبكم رقم [%(order_name)s] لسيارتك [%(plate)s].\n\n"
                "يرجى الحضور لإستلام السيارة.\n\n"
                "شكرًا لثقتك بنا!"
            ) % {
                "order_name": self.name or "",
                "plate": self.vehicle_license_plate or "",
            }
            lang = (self.partner_id.lang or "en_US").lower()

            if lang.startswith("ar_001"):
                message_text = message_text_ar
            else:
                message_text = message_text_en
            self._send_sms_message(phone, message_text)

    def action_cancel(self):
        self.ensure_one()
        self.state = "cancelled"

    def action_view_picking(self):
        self.ensure_one()
        action = self.env["ir.actions.actions"]._for_xml_id(
            "stock.action_picking_tree_internal")
        action["views"] = [(False, "form")]
        action["res_id"] = self.picking_id.id
        return action

    def action_view_appointment(self):
        self.ensure_one()
        action = self.env["ir.actions.actions"]._for_xml_id(
            "appointment_management.car_appointment_action")
        action["views"] = [(False, "form")]
        action["res_id"] = self.appointment_id.id
        return action

    def action_view_car_checkin_id(self):
        self.ensure_one()
        action = self.env["ir.actions.actions"]._for_xml_id(
            "cars_management.car_checkin_action")
        action["views"] = [(False, "form")]
        sub_orders_count = self.env["car.work.order"].search_count([
            ("parent_id", "=", self.id)
        ])

    def action_view_car_checkout_id(self):
        self.ensure_one()
        action = self.env["ir.actions.actions"]._for_xml_id(
            "cars_management.car_checkout_action")
        action["views"] = [(False, "form")]
        action["res_id"] = self.car_checkout_id.id
        return action

    @api.model
    def retrieve_dashboard(self):
        self.check_access_rights("read")
        result = {}
        app = self.env["car.work.order"]
        result["all_waiting"] = app.search_count(
            [("state", "in", ("new", "confirmed"))])
        result["all_progress"] = app.search_count(
            [("state", "in", ("progress", "quality", "quality_confirmed"))])
        result["all_done"] = app.search_count([("state", "=", "done")])
        return result

    def _send_sms_message(self, phone_number, message_text):
        """Helper to send SMS using the existing wizard."""
        wizard = (
            self.env["sms.message.wizard"]
            .with_context(active_id=self.id, active_model=self._name, lang=self.partner_id.lang)
            .create(
                {
                    "mobile": phone_number,
                    "message": message_text,
                }
            )
        )
        try:
            return wizard.send_sms()
        except Exception as e:
            raise ValidationError(
                _("Failed to send SMS: %s") % str(e)) from None


class CarWorkOrderService(models.Model):
    _name = "car.workorder.service"
    _description = "Workorder Service"
    _rec_name = "product_id"

    product_id = fields.Many2one(
        "product.product", string="Service", required=True, domain="[('type', '=', 'service')]"
    )
    workorder_id = fields.Many2one("car.work.order", string="Workorder")
    branch_id = fields.Many2one(
        'hr.department', related='workorder_id.branch_id', store=False, string='Branch')
    workshop_id = fields.Many2one("car.workshop")
    workcenter_id = fields.Many2one("car.workcenter")
    expected_duration = fields.Float()
    staff_ids = fields.Many2many(
        'hr.employee', 'car_workorder_service_staff_rel', 'service_id', 'employee_id', string='Staff', required=True)

    @api.onchange('workorder_id')
    def _onchange_workorder_staff(self):
        """Filter staff by the selected workorder branch."""
        self.ensure_one()
        if self.workorder_id and self.workorder_id.branch_id:
            branch = self.workorder_id.branch_id
            self.staff_ids = self.staff_ids.filtered(
                lambda emp: emp.branch_id == branch)
            return {'domain': {'staff_ids': [('branch_id', '=', branch.id)]}}

        self.staff_ids = [(5, 0, 0)]
        return {'domain': {'staff_ids': [('id', '=', False)]}}
    expected_finish_date = fields.Datetime()
    date_start = fields.Datetime()
    date_end = fields.Datetime()
    pause_start = fields.Datetime(string="Pause Start", readonly=True)
    pause_duration = fields.Float(
        string="Pause Duration (seconds)", default=0.0, readonly=True)
    state = fields.Selection(
        [
            ("waiting", "Waiting"),
            ("ready", "Ready"),
            ("progress", "In Progress"),
            ("done", "Finished"),
            ("cancel", "Cancelled"),
        ],
        string="Status",
        default="waiting",
        copy=False,
        readonly=True,
    )
    duration_hours = fields.Float(
        string="Duration (hours)", compute="_compute_duration_hours", store=True)

    def action_start(self):
        self.ensure_one()
        # If already on break, resume work
        if self.pause_start:
            now = fields.Datetime.now()
            pause_time = (
                now - self.pause_start).total_seconds() if self.pause_start else 0
            self.pause_duration += pause_time
            self.pause_start = False
        # If not yet started, start normally
        elif not self.date_start:
            self.date_start = fields.Datetime.now()
        self.state = "progress"
        return True

    def action_break(self):
        self.ensure_one()
        now = fields.Datetime.now()
        # If already on break, resume work (equivalent to start)
        if self.pause_start:
            pause_time = (now - self.pause_start).total_seconds()
            self.pause_duration += pause_time
            self.pause_start = False
            self.state = "progress"
        else:
            # Start the break
            self.pause_start = now
            self.state = "waiting"
        return True

    def action_finish(self):
        self.ensure_one()
        now = fields.Datetime.now()
        # If on break at the time of finish, add the last break
        if self.pause_start:
            pause_time = (now - self.pause_start).total_seconds()
            self.pause_duration += pause_time
            self.pause_start = False
        self.date_end = now
        self.state = "done"
        return True

    @api.depends('date_start', 'date_end', 'pause_duration')
    def _compute_duration_hours(self):
        for rec in self:
            if rec.date_start and rec.date_end:
                total_seconds = (rec.date_end - rec.date_start).total_seconds()
                # Subtract the break duration
                total_seconds -= rec.pause_duration or 0.0
                rec.duration_hours = max(total_seconds, 0) / 3600.0
            else:
                rec.duration_hours = 0.0


class CarWorkOrderProduct(models.Model):
    _name = "car.workorder.product"
    _description = "Workorder product"
    _rec_name = "product_id"

    product_id = fields.Many2one(
        "product.product", string="Product", domain="[('detailed_type', '!=', 'service')]")
    service_id = fields.Many2one("product.product", string="Service")
    quantity = fields.Float()
    workorder_id = fields.Many2one("car.work.order", string="Workorder")
