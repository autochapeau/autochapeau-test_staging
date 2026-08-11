import logging
import math
import random
import re
from urllib.parse import parse_qs

import requests

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError
from odoo.tools.safe_eval import safe_eval

_logger = logging.getLogger(__name__)


class ResPartner(models.Model):
    _inherit = "res.partner"

    # ── Contact type ──────────────────────────────────────────────────
    contact_partner_type = fields.Selection(
        [
            ("customer", "Customer"),
            ("supplier", "Supplier"),
            ("employee", "Employee"),
        ],
        default="customer",
        string="Contact Type",
    )

    # ── City ──────────────────────────────────────────────────────────
    city_id = fields.Many2one(
        "res.city",
        string="City",
        ondelete="restrict",
        domain="[('country_id', '=', country_id)]",
    )

    # ── Subordinate / Supervisor ──────────────────────────────────────
    # Hierarchy rule: Contract (supervisor) → Internal (subordinate) only.
    supervisor_id = fields.Many2one(
        "res.partner",
        string="Supervisor",
        ondelete="set null",
        index=True,
        domain="[('partner_type', '=', 'contract')]",
        help="Must be a Contract contact. Only Internal contacts can have a "
             "supervisor. This does not affect invoicing (unlike parent_id).",
    )
    subordinate_ids = fields.One2many(
        "res.partner",
        "supervisor_id",
        string="Subordinates",
        domain="[('partner_type', '=', 'internal')]",
    )

    # ── Smart button counters ─────────────────────────────────────────
    appointment_count = fields.Integer(compute="_compute_appointment_count")
    checkin_count = fields.Integer(compute="_compute_checkin_checkout_count")
    checkout_count = fields.Integer(compute="_compute_checkin_checkout_count")
    workorder_count = fields.Integer(compute="_compute_workorder_count")
    payment_count = fields.Integer(compute="_compute_payment_count")
    invoice_count = fields.Integer(compute="_compute_invoice_count")
    partner_sale_order_count = fields.Integer(
        compute="_compute_partner_sale_order_count",
        string="Sales Orders",
    )

    # ── Mobile OTP ────────────────────────────────────────────────────
    mobile_otp_input = fields.Char(
        string="OTP Code",
        copy=False,
        help="Enter the verification code sent to the customer's mobile.",
    )
    mobile_verified = fields.Boolean(
        string="Mobile Verified",
        default=False,
        copy=False,
        help="Set automatically after a successful OTP verification. "
             "Unverified customers are archived until verified.",
    )
    mobile_normalized = fields.Char(
        compute="_compute_mobile_normalized",
        store=True,
        index=True,
    )
    email_normalized_unique = fields.Char(
        compute="_compute_email_normalized_unique",
        store=True,
        index=True,
    )

    # ── City helpers ──────────────────────────────────────────────────

    @api.onchange("city_id")
    def _onchange_city_id(self):
        self.city = self.city_id.name if self.city_id else False
        if self.city_id and self.city_id.country_id:
            self.country_id = self.city_id.country_id

    @api.onchange("country_id")
    def _onchange_country_id_clear_city(self):
        if self.city_id and self.city_id.country_id != self.country_id:
            self.city_id = False
            self.city = False

    @api.model
    def _sync_city_from_city_id(self, vals):
        if "city_id" not in vals:
            return
        city_id = vals.get("city_id")
        if city_id:
            city = self.env["res.city"].browse(city_id)
            vals["city"] = city.name
            if city.country_id and not vals.get("country_id"):
                vals["country_id"] = city.country_id.id
        else:
            vals["city"] = False

    # ── Subordinate helpers ───────────────────────────────────────────

    @api.constrains("supervisor_id")
    def _check_supervisor_recursion(self):
        if not self._check_recursion(parent="supervisor_id"):
            raise ValidationError(_(
                "A contact cannot be its own supervisor (directly or indirectly)."
            ))

    @api.constrains("supervisor_id", "partner_type")
    def _check_supervisor_hierarchy(self):
        for partner in self:
            if not partner.supervisor_id:
                continue
            if partner.partner_type != "internal":
                raise ValidationError(_(
                    "Only Internal contacts can have a supervisor. "
                    "Hierarchy must be Contract → Internal."
                ))
            if partner.supervisor_id.partner_type != "contract":
                raise ValidationError(_(
                    "The supervisor must be a Contract contact. "
                    "Hierarchy must be Contract → Internal."
                ))

    @api.constrains("partner_type")
    def _check_partner_type_has_subordinates(self):
        for partner in self:
            if partner.partner_type != "contract" and partner.subordinate_ids:
                raise ValidationError(_(
                    "Only Contract contacts can have subordinates. "
                    "Hierarchy must be Contract → Internal."
                ))

    def _compute_appointment_count(self):
        Appointment = self.env["car.appointment"]
        for partner in self:
            partner.appointment_count = Appointment.search_count(
                [("partner_id", "=", partner.id)]
            )

    def _compute_partner_sale_order_count(self):
        SaleOrder = self.env["sale.order"]
        for partner in self:
            partner.partner_sale_order_count = SaleOrder.search_count(
                [("partner_id", "=", partner.id)]
            )

    def _action_open_related_popup(self, xmlid=None, *, name=False, res_model=False,
                                   domain=None, context=None, list_view_xmlid=None,
                                   form_view_xmlid=None):
        """Open a related list/form in a large dialog with working New + record open."""
        self.ensure_one()
        if xmlid:
            action = dict(self.env["ir.actions.act_window"]._for_xml_id(xmlid))
        else:
            action = {
                "type": "ir.actions.act_window",
                "name": name,
                "res_model": res_model,
            }

        list_view_id = (
            self.env.ref(list_view_xmlid).id if list_view_xmlid else False
        )
        form_view_id = (
            self.env.ref(form_view_xmlid).id if form_view_xmlid else False
        )

        action.update({
            "domain": domain or [],
            "view_mode": "list,form",
            "views": [
                (list_view_id, "list"),
                (form_view_id, "form"),
            ],
            "view_id": False,
        })

        raw_ctx = action.get("context") or {}
        if isinstance(raw_ctx, str):
            eval_ctx = self.env["ir.actions.actions"]._get_eval_context()
            eval_ctx.update({
                "active_id": self.id,
                "active_ids": self.ids,
                "active_model": self._name,
                "uid": self.env.uid,
                "context": dict(self.env.context),
            })
            ctx = safe_eval(raw_ctx, eval_ctx)
        else:
            ctx = dict(raw_ctx)
        ctx.update({
            "dialog_size": "extra-large",
            "form_view_initial_mode": "edit",
        })
        if context:
            ctx.update(context)
        action["context"] = ctx
        return action

    def action_view_partner_sale_orders(self):
        return self._action_open_related_popup(
            "sale.act_res_partner_2_sale_order",
            domain=[("partner_id", "child_of", self.id)],
            context={"default_partner_id": self.id},
        )

    def action_view_partner_cars(self):
        return self._action_open_related_popup(
            "cars_management.fleet_vehicle_action",
            domain=[("partner_id", "=", self.id)],
            context={"default_partner_id": self.id},
            list_view_xmlid="cars_management.fleet_vehicle_view_tree",
            form_view_xmlid="cars_management.fleet_vehicle_view_form",
        )

    def _compute_checkin_checkout_count(self):
        Checkin = self.env["car.checkin"]
        Checkout = self.env["car.checkout"]
        for partner in self:
            partner.checkin_count = Checkin.search_count(
                [("partner_id", "=", partner.id)]
            )
            partner.checkout_count = Checkout.search_count(
                [("partner_id", "=", partner.id)]
            )

    def action_view_appointments(self):
        return self._action_open_related_popup(
            "appointment_management.car_appointment_action",
            domain=[("partner_id", "=", self.id)],
            context={"default_partner_id": self.id},
        )

    def action_view_checkins(self):
        return self._action_open_related_popup(
            "cars_management.car_checkin_action",
            domain=[("partner_id", "=", self.id)],
            context={"default_partner_id": self.id},
        )

    def action_view_checkouts(self):
        return self._action_open_related_popup(
            "cars_management.car_checkout_action",
            domain=[("partner_id", "=", self.id)],
            context={"default_partner_id": self.id},
        )

    def _compute_workorder_count(self):
        WorkOrder = self.env["car.work.order"]
        for partner in self:
            partner.workorder_count = WorkOrder.search_count(
                [("partner_id", "=", partner.id)]
            )

    def action_view_workorders(self):
        return self._action_open_related_popup(
            "work_orders.car_work_order_action",
            domain=[("partner_id", "=", self.id)],
            context={"default_partner_id": self.id},
        )

    def _compute_payment_count(self):
        Payment = self.env["account.payment"]
        for partner in self:
            partner.payment_count = Payment.search_count(
                [("partner_id", "=", partner.id)]
            )

    def action_view_payments(self):
        return self._action_open_related_popup(
            "account.action_account_payments",
            domain=[("partner_id", "=", self.id)],
            context={
                "default_partner_id": self.id,
                "default_payment_type": "inbound",
                "default_partner_type": "customer",
                "default_move_journal_types": ("bank", "cash"),
            },
        )

    def _compute_invoice_count(self):
        Move = self.env["account.move"]
        for partner in self:
            partner.invoice_count = Move.search_count(
                [
                    ("partner_id", "child_of", partner.id),
                    ("move_type", "in", ("out_invoice", "out_refund")),
                ]
            )

    def action_view_invoices(self):
        return self._action_open_related_popup(
            "account.action_move_out_invoice_type",
            domain=[
                ("partner_id", "child_of", self.id),
                ("move_type", "in", ("out_invoice", "out_refund")),
            ],
            context={
                "default_partner_id": self.id,
                "default_move_type": "out_invoice",
            },
        )

    # ── OTP helpers ───────────────────────────────────────────────────

    @api.depends("mobile")
    def _compute_mobile_normalized(self):
        for partner in self:
            partner.mobile_normalized = partner._normalize_mobile(partner.mobile) or False

    @api.depends("email")
    def _compute_email_normalized_unique(self):
        for partner in self:
            email = (partner.email or "").strip().lower()
            partner.email_normalized_unique = email or False

    @api.model
    def _normalize_mobile(self, mobile):
        if not mobile:
            return ""
        value = re.sub(r"[\s\-()]", "", str(mobile).strip())
        if value.startswith("00"):
            value = "+" + value[2:]
        return value

    @api.model
    def _otp_storage_key(self, mobile):
        return f"partner_mobile_otp_{self._normalize_mobile(mobile)}"

    @api.model
    def _generate_otp_code(self):
        digits = "0123456789"
        return "".join(digits[math.floor(random.random() * 10)] for _ in range(4))

    @api.model
    def _store_mobile_otp(self, mobile, otp):
        _logger.warning("===== OTP for %s = %s =====", mobile, otp)
        print("===== OTP for %s = %s =====" % (mobile, otp), flush=True)
        self.env["ir.config_parameter"].sudo().set_param(
            self._otp_storage_key(mobile), otp
        )

    @api.model
    def _get_stored_mobile_otp(self, mobile):
        icp = self.env["ir.config_parameter"].sudo()
        norm = self._normalize_mobile(mobile)
        return (
            icp.get_param(self._otp_storage_key(mobile))
            or icp.get_param(f"register_{norm}_otp")
            or icp.get_param(f"register_{mobile}_otp")
        )

    @api.model
    def _clear_stored_mobile_otp(self, mobile):
        self.env["ir.config_parameter"].sudo().set_param(
            self._otp_storage_key(mobile), False
        )

    @api.model
    def _format_phone_for_sms(self, mobile, country=None):
        phone = self._normalize_mobile(mobile)
        if not phone:
            return ""
        if phone.startswith("+"):
            return phone
        country_code = country.phone_code if country else ""
        if country_code:
            return f"+{country_code}{phone}"
        return phone

    @api.model
    def _send_otp_sms_message(self, phone, message, partner=None):
        """Send OTP SMS via Infinito without requiring an existing chatter record."""
        icp = self.env["ir.config_parameter"].sudo()
        params = {
            "clientid": icp.get_param("infinito_client_id", ""),
            "clientpassword": icp.get_param("infinito_client_password", ""),
            "from": "AutoChapeau",
            "to": phone,
            "text": message,
        }
        try:
            response = requests.get(
                "https://api.goinfinito.me/unified/v2/send",
                params=params,
                timeout=10,
            )
            parsed = parse_qs(response.text)
            status = parsed.get("statustext") or []
            if status == "Success" or (isinstance(status, list) and status and status[0] == "Success"):
                if partner and partner.id:
                    partner.message_post(
                        body=message,
                        subject=_("SMS Sent"),
                        message_type="comment",
                        subtype_xmlid="mail.mt_comment",
                    )
                return True
            raise ValidationError(_("Failed to send SMS: %s") % response.text)
        except ValidationError:
            raise
        except Exception as exc:
            _logger.exception("Partner OTP SMS failed")
            raise ValidationError(_("Failed to send SMS: %s") % str(exc)) from None

    @api.model
    def _assert_mobile_otp_valid(self, mobile, otp_input):
        if not otp_input or not str(otp_input).strip():
            raise ValidationError(_(
                "Please enter the OTP code sent to the mobile number before saving."
            ))
        stored = self._get_stored_mobile_otp(mobile)
        if not stored or str(otp_input).strip() != str(stored).strip():
            raise ValidationError(_("Incorrect OTP code."))
        self._clear_stored_mobile_otp(mobile)

    def _skips_customer_mobile_otp(self, partner_type=None, parent_id=None, supervisor_id=None):
        """True when OTP must not be required for this partner shape."""
        if partner_type == "contract":
            return True
        if parent_id or supervisor_id:
            return True
        return False

    def _requires_customer_mobile_otp(
        self,
        contact_type,
        mobile,
        partner_type=None,
        parent_id=None,
        supervisor_id=None,
    ):
        """OTP is required for customers with a mobile.

        Skipped for Contract partners, parent-linked contacts, and subordinates
        created under a supervisor (supervisor_id).
        """
        if self.env.context.get("skip_partner_mobile_otp"):
            return False
        if self._skips_customer_mobile_otp(partner_type, parent_id, supervisor_id):
            return False
        return contact_type == "customer" and bool(mobile)

    @api.model
    def _otp_input_provided(self, otp_input):
        return bool(otp_input and str(otp_input).strip())

    @api.model
    def _apply_customer_active_from_verified(
        self,
        vals,
        contact_type,
        verified,
        partner_type=None,
        parent_id=None,
        supervisor_id=None,
    ):
        """Archive unverified customers; reactivate when verified.

        Contract, subordinate (supervisor_id), and child contacts are never archived for OTP.
        """
        if contact_type != "customer" or verified is None:
            return
        if self._skips_customer_mobile_otp(partner_type, parent_id, supervisor_id):
            vals["active"] = True
            return
        vals["active"] = bool(verified)

    # ── Create / Write (city sync + OTP verification) ─────────────────
    # OTP is validated only when the user enters a code. Saving without a
    # code is allowed so "Send OTP" can auto-save first. Unverified
    # customers stay archived until OTP succeeds.
    # Contract / subordinate / child-of-parent: no OTP required, but that
    # does NOT mean the mobile is verified.

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            self._sync_city_from_city_id(vals)
            contact_type = vals.get("contact_partner_type") or self.env.context.get(
                "default_contact_partner_type", "customer"
            )
            partner_type = vals.get("partner_type") or self.env.context.get(
                "default_partner_type", "external"
            )
            parent_id = vals.get("parent_id")
            supervisor_id = vals.get("supervisor_id") or self.env.context.get(
                "default_supervisor_id"
            )
            mobile = vals.get("mobile")
            otp_input = vals.get("mobile_otp_input")
            if contact_type == "customer":
                if self._skips_customer_mobile_otp(
                    partner_type, parent_id, supervisor_id
                ):
                    # Skip OTP UI/requirement, keep mobile unverified, stay active.
                    vals["mobile_verified"] = False
                    vals["active"] = True
                elif self._requires_customer_mobile_otp(
                    contact_type, mobile, partner_type, parent_id, supervisor_id
                ):
                    if self._otp_input_provided(otp_input):
                        self._assert_mobile_otp_valid(mobile, otp_input)
                        vals["mobile_verified"] = True
                    else:
                        vals["mobile_verified"] = False
                    self._apply_customer_active_from_verified(
                        vals,
                        contact_type,
                        vals.get("mobile_verified", False),
                        partner_type,
                        parent_id,
                        supervisor_id,
                    )
                else:
                    vals.setdefault("mobile_verified", False)
                    self._apply_customer_active_from_verified(
                        vals,
                        contact_type,
                        vals.get("mobile_verified", False),
                        partner_type,
                        parent_id,
                        supervisor_id,
                    )
            if "mobile_otp_input" in vals:
                vals["mobile_otp_input"] = False
        return super().create(vals_list)

    def write(self, vals):
        vals = dict(vals)
        self._sync_city_from_city_id(vals)
        otp_input = vals.get("mobile_otp_input")
        otp_provided = self._otp_input_provided(otp_input)

        for partner in self:
            contact_type = vals.get(
                "contact_partner_type", partner.contact_partner_type
            )
            partner_type = vals.get("partner_type", partner.partner_type)
            parent_id = (
                vals["parent_id"] if "parent_id" in vals else partner.parent_id.id
            )
            supervisor_id = (
                vals["supervisor_id"]
                if "supervisor_id" in vals
                else partner.supervisor_id.id
            )
            new_mobile = vals["mobile"] if "mobile" in vals else partner.mobile
            old_norm = partner._normalize_mobile(partner.mobile)
            new_norm = partner._normalize_mobile(new_mobile)
            mobile_changed = "mobile" in vals and new_norm != old_norm

            # Skip OTP for contract / subordinate / child: stay active.
            # Do not force mobile_verified False here — Extra Order wizard may
            # verify the subordinate later without requiring OTP on the form.
            if contact_type == "customer" and self._skips_customer_mobile_otp(
                partner_type, parent_id, supervisor_id
            ):
                vals["active"] = True
                if mobile_changed and "mobile_verified" not in vals:
                    vals["mobile_verified"] = False
                continue

            requires_otp = self._requires_customer_mobile_otp(
                contact_type, new_mobile, partner_type, parent_id, supervisor_id
            )

            if otp_provided and requires_otp:
                self._assert_mobile_otp_valid(new_mobile, otp_input)
                vals["mobile_verified"] = True
            elif mobile_changed and requires_otp and not otp_provided:
                vals["mobile_verified"] = False
            elif mobile_changed and not new_mobile:
                vals["mobile_verified"] = False

            if contact_type == "customer" and "mobile_verified" in vals:
                self._apply_customer_active_from_verified(
                    vals,
                    contact_type,
                    vals["mobile_verified"],
                    partner_type,
                    parent_id,
                    supervisor_id,
                )

        if "mobile_otp_input" in vals:
            vals["mobile_otp_input"] = False
        return super().write(vals)

    def action_open_send_otp_wizard(self):
        """Compatibility alias: send OTP directly (no wizard)."""
        return self.action_send_mobile_otp()

    def action_send_mobile_otp(self):
        """Send OTP using mobile + country from the partner form (no wizard)."""
        self.ensure_one()
        if self.contact_partner_type != "customer":
            raise ValidationError(_("OTP verification is only required for customers."))
        if self._skips_customer_mobile_otp(
            self.partner_type,
            self.parent_id.id if self.parent_id else False,
            self.supervisor_id.id if self.supervisor_id else False,
        ):
            raise ValidationError(_(
                "OTP verification is not required for Contract, subordinate, "
                "or parent-linked contacts."
            ))
        if not self.mobile:
            raise ValidationError(_("Please enter the mobile number first."))
        if not self.country_id:
            raise ValidationError(_("Please select the country first."))
        otp = self._generate_otp_code()
        self._store_mobile_otp(self.mobile, otp)
        phone = self._format_phone_for_sms(self.mobile, self.country_id)
        message = _("Your verification code is: %s") % otp
        self._send_otp_sms_message(phone, message, partner=self)
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("OTP Sent"),
                "message": _("A verification code has been sent to %s. OTP: " + otp) % phone,
                "type": "success",
                "sticky": False,
            },
        }
