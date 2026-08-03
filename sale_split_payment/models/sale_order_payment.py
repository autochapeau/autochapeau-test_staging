import logging
import uuid

import requests

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)

TABBY_REJECTION_MESSAGES = {
    "order_amount_too_low": (
        "The purchase amount is below the minimum amount required to use Tabby."
    ),
    "order_amount_too_high": (
        "This purchase is above the current spending limit with Tabby."
    ),
    "not_available": (
        "Sorry, Tabby is unable to approve this purchase. Please use another payment method."
    ),
}


class SaleOrderPayment(models.Model):
    _name = "sale.order.payment"
    _description = "Sale Order Collection Payment"
    _order = "create_date desc, id desc"
    _check_company_auto = True

    name = fields.Char(
        default=lambda self: _("New"),
        readonly=True,
        copy=False,
    )
    sale_order_id = fields.Many2one(
        "sale.order",
        required=True,
        ondelete="cascade",
        index=True,
        check_company=True,
    )
    partner_id = fields.Many2one(
        related="sale_order_id.partner_id",
        store=True,
        index=True,
    )
    company_id = fields.Many2one(
        related="sale_order_id.company_id",
        store=True,
        index=True,
    )
    currency_id = fields.Many2one(
        related="sale_order_id.currency_id",
        store=True,
    )
    amount = fields.Monetary(required=True, currency_field="currency_id")
    collection_method_id = fields.Many2one(
        "sale.collection.method",
        string="Payment Method",
        required=True,
        check_company=True,
        domain="[('company_id', '=', company_id), ('active', '=', True)]",
    )
    processing_type = fields.Selection(
        related="collection_method_id.processing_type",
        store=True,
        index=True,
    )
    journal_id = fields.Many2one(
        "account.journal",
        domain="[('type', 'in', ('cash', 'bank')), ('company_id', '=', company_id)]",
        check_company=True,
    )
    provider_reference = fields.Char(
        string="Reference",
        copy=False,
        help="Bank transfer / cheque / terminal reference entered by the cashier.",
    )
    state = fields.Selection(
        [
            ("draft", "Draft"),
            ("processing", "Processing"),
            ("pending", "Pending"),
            ("paid", "Paid"),
            ("failed", "Failed"),
            ("needs_review", "Needs Review"),
            ("cancelled", "Cancelled"),
        ],
        default="draft",
        required=True,
        readonly=True,
        index=True,
    )
    external_reference = fields.Char(copy=False, index=True, readonly=True)
    checkout_url = fields.Char(copy=False, readonly=True)
    status_url = fields.Char(copy=False, readonly=True)
    provider_status = fields.Char(copy=False, readonly=True)
    error_message = fields.Text(copy=False, readonly=True)
    account_payment_id = fields.Many2one(
        "account.payment",
        copy=False,
        readonly=True,
        check_company=True,
    )
    access_token = fields.Char(
        default=lambda self: str(uuid.uuid4()),
        required=True,
        copy=False,
        readonly=True,
        index=True,
    )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("name", _("New")) == _("New"):
                vals["name"] = self.env["ir.sequence"].next_by_code(
                    "sale.order.payment"
                ) or _("New")
            method = self.env["sale.collection.method"].browse(
                vals.get("collection_method_id")
            )
            if method and not vals.get("journal_id"):
                vals["journal_id"] = method.resolve_journal().id
        return super().create(vals_list)

    @api.onchange("collection_method_id")
    def _onchange_collection_method_id(self):
        for payment in self:
            if payment.collection_method_id:
                payment.journal_id = payment.collection_method_id.resolve_journal()

    @api.constrains("amount")
    def _check_positive_amount(self):
        for payment in self:
            if payment.amount <= 0:
                raise ValidationError(_("The payment amount must be greater than zero."))

    def unlink(self):
        if any(payment.state not in ("draft", "failed", "cancelled") for payment in self):
            raise UserError(_("Only draft, failed, or cancelled payments can be deleted."))
        return super().unlink()

    def action_process(self):
        self.ensure_one()
        if self.state not in ("draft", "failed", "needs_review"):
            raise UserError(
                _("Only draft, failed, or needs-review payments can be processed.")
            )
        if not self.collection_method_id:
            raise UserError(_("Please select a payment method."))
        if (
            self.collection_method_id.require_reference
            and not self.provider_reference
        ):
            raise UserError(_("Please enter the payment reference."))
        self.write({"state": "processing", "error_message": False})
        processing_type = self.collection_method_id.processing_type
        if processing_type == "manual":
            return self._mark_provider_paid(
                self.provider_reference or _("Manual payment received")
            )
        if processing_type == "terminal":
            return self._send_card_terminal_payment()
        if processing_type == "tabby":
            return self._create_tabby_checkout()
        raise UserError(_("Unsupported payment method processing type."))

    def action_refresh_status(self):
        self.ensure_one()
        if self.processing_type == "terminal":
            return self._refresh_card_terminal_status()
        if self.processing_type == "tabby":
            return self._refresh_tabby_status()
        raise UserError(_("This payment method has no remote status."))

    def action_open_checkout(self):
        self.ensure_one()
        if not self.checkout_url:
            raise UserError(_("No checkout URL is available."))
        return {
            "type": "ir.actions.act_url",
            "url": self.checkout_url,
            "target": "new",
        }

    def action_open_account_payment(self):
        self.ensure_one()
        if not self.account_payment_id:
            raise UserError(_("No customer payment has been created yet."))
        return {
            "type": "ir.actions.act_window",
            "name": _("Customer Payment"),
            "res_model": "account.payment",
            "res_id": self.account_payment_id.id,
            "view_mode": "form",
            "views": [(False, "form")],
            "target": "current",
        }

    def action_cancel(self):
        for payment in self:
            if payment.state == "paid":
                raise UserError(
                    _(
                        "A posted payment must be reversed from Accounting; "
                        "it cannot be cancelled here."
                    )
                )
            payment.state = "cancelled"

    def action_reconcile(self):
        self._reconcile_available_invoices(raise_if_missing=True)
        return True

    def _get_config(self, key, default=False):
        return self.env["ir.config_parameter"].sudo().get_param(key, default)

    def _get_journal(self):
        self.ensure_one()
        journal = self.journal_id or self.collection_method_id.resolve_journal()
        if not journal:
            raise UserError(
                _(
                    "Configure a journal on the payment method '%s' "
                    "(Sales > Configuration > Collection Methods)."
                )
                % self.collection_method_id.display_name
            )
        return journal

    def _create_advance_payment(self):
        """Create and post a customer payment that appears on the Partner Ledger."""
        self.ensure_one()
        if self.account_payment_id:
            return self.account_payment_id
        journal = self._get_journal()
        method_line = self.collection_method_id.get_payment_method_line(journal)
        if not method_line:
            raise UserError(
                _(
                    "Journal %s has no inbound payment method. Add one under "
                    "Accounting > Configuration > Journals > Incoming Payments."
                )
                % journal.display_name
            )
        reference_bits = [self.name, self.sale_order_id.name]
        if self.provider_reference:
            reference_bits.append(self.provider_reference)
        if self.external_reference:
            reference_bits.append(self.external_reference)
        payment = self.env["account.payment"].sudo().create(
            {
                "payment_type": "inbound",
                "partner_type": "customer",
                "partner_id": self.partner_id.id,
                "amount": self.amount,
                "currency_id": self.currency_id.id,
                "date": fields.Date.context_today(self),
                "journal_id": journal.id,
                "payment_method_line_id": method_line.id,
                "ref": " / ".join(reference_bits),
            }
        )
        payment.sudo().action_post()
        self.account_payment_id = payment
        return payment

    def _mark_provider_paid(self, provider_status):
        self.ensure_one()
        try:
            payment = self._create_advance_payment()
        except Exception as error:
            _logger.exception("Could not create advance payment for %s", self.name)
            self.write(
                {
                    "state": "needs_review",
                    "provider_status": provider_status,
                    "error_message": str(error),
                }
            )
            return False
        self.write(
            {
                "state": "paid",
                "provider_status": provider_status,
                "error_message": False,
                "account_payment_id": payment.id,
            }
        )
        self._reconcile_available_invoices()
        return True

    def _terminal_headers(self):
        token = self._get_config("sale_split_payment.card_terminal_token")
        headers = {"Content-Type": "application/json"}
        if token:
            headers["Authorization"] = "Bearer %s" % token
        return headers

    def _terminal_timeout(self):
        try:
            return max(
                int(self._get_config("sale_split_payment.card_terminal_timeout", 60)),
                1,
            )
        except (TypeError, ValueError):
            return 60

    def _send_card_terminal_payment(self):
        self.ensure_one()
        # Validate journal first so we do not charge the card without bookkeeping.
        self._get_journal()
        terminal_url = self._get_config("sale_split_payment.card_terminal_url")
        if not terminal_url:
            self.write(
                {
                    "state": "failed",
                    "error_message": _("Card terminal API URL is not configured."),
                }
            )
            return False
        payload = {
            "reference": self.name,
            "amount": float(self.amount),
            "currency": self.currency_id.name,
            "sale_order": self.sale_order_id.name,
            "partner": self.partner_id.name,
        }
        try:
            response = requests.post(
                terminal_url,
                json=payload,
                headers=self._terminal_headers(),
                timeout=self._terminal_timeout(),
            )
            response.raise_for_status()
            result = response.json()
        except (requests.RequestException, ValueError) as error:
            self.write({"state": "failed", "error_message": str(error)})
            return False
        return self._apply_terminal_result(result)

    def _apply_terminal_result(self, result):
        self.ensure_one()
        status = str(result.get("status", "")).lower()
        reference = (
            result.get("transaction_id")
            or result.get("reference")
            or result.get("id")
        )
        values = {
            "external_reference": reference,
            "provider_status": status,
            "status_url": result.get("status_url"),
            "error_message": result.get("message"),
        }
        if status in ("approved", "success", "paid", "completed"):
            self.write(values)
            if reference:
                self._mark_provider_paid(status)
            else:
                self.write(
                    {
                        "state": "needs_review",
                        "error_message": _(
                            "The terminal approved the charge but did not return "
                            "a transaction reference."
                        ),
                    }
                )
        elif status in ("pending", "processing"):
            values["state"] = "pending"
            self.write(values)
        else:
            values["state"] = "failed"
            self.write(values)
        return False

    def _refresh_card_terminal_status(self):
        self.ensure_one()
        if not self.external_reference:
            raise UserError(_("The terminal transaction has no external reference."))
        status_template = self._get_config(
            "sale_split_payment.card_terminal_status_url"
        )
        status_url = self.status_url or (
            status_template.format(reference=self.external_reference)
            if status_template
            else False
        )
        if not status_url:
            raise UserError(_("Card terminal status URL is not configured."))
        try:
            response = requests.get(
                status_url,
                headers=self._terminal_headers(),
                timeout=self._terminal_timeout(),
            )
            response.raise_for_status()
            result = response.json()
        except (requests.RequestException, ValueError) as error:
            self.error_message = str(error)
            return False
        return self._apply_terminal_result(result)

    def _tabby_headers(self):
        secret_key = self._get_config("tabby.secret_key")
        if not secret_key:
            raise UserError(_("Tabby secret key is not configured."))
        return {
            "Authorization": "Bearer %s" % secret_key,
            "Content-Type": "application/json",
        }

    def _tabby_rejection_message(self, result):
        products = (
            result.get("configuration", {}).get("products")
            or result.get("configuration", {}).get("available_products")
            or {}
        )
        installments = products.get("installments") or {}
        if isinstance(installments, list):
            reason = False
        else:
            reason = installments.get("rejection_reason")
        if reason in TABBY_REJECTION_MESSAGES:
            return _(TABBY_REJECTION_MESSAGES[reason])
        status = result.get("status")
        if status:
            return _("Tabby rejected the payment (status: %s).") % status
        return _("Tabby did not return a payment ID and checkout URL.")

    def _create_tabby_checkout(self):
        self.ensure_one()
        # Validate journal before opening Tabby so posting can succeed later.
        self._get_journal()
        checkout_url = self._get_config("tabby.checkout_api_url")
        merchant_code = self._get_config("tabby.merchant_code")
        if not checkout_url or not merchant_code:
            self.write(
                {
                    "state": "failed",
                    "error_message": _(
                        "Tabby checkout URL or merchant code is not configured."
                    ),
                }
            )
            return False
        base_url = self._get_config("web.base.url", "").rstrip("/")
        callback_url = "%s/sale_split_payment/tabby/return/%s" % (
            base_url,
            self.access_token,
        )
        partner = self.partner_id
        environment = self._get_config("tabby.environment", "test")
        phone = (
            "500000001"
            if environment == "test"
            else (partner.mobile or partner.phone)
        )
        email = (
            "card.success@tabby.ai"
            if environment == "test"
            else partner.email
        )
        payload = {
            "payment": {
                "amount": "%.2f" % self.amount,
                "currency": self.currency_id.name,
                "description": self.sale_order_id.name,
                "buyer": {
                    "phone": phone or "",
                    "email": email or "",
                    "name": partner.name or "",
                    "dob": "",
                },
                "buyer_history": {
                    "registered_since": (
                        partner.create_date.strftime("%Y-%m-%dT%H:%M:%SZ")
                        if partner.create_date
                        else "2019-08-24T14:15:22Z"
                    ),
                    "loyalty_level": 0,
                    "wishlist_count": 0,
                    "is_social_networks_connected": False,
                    "is_phone_number_verified": bool(partner.mobile or partner.phone),
                    "is_email_verified": bool(partner.email),
                },
                "order": {
                    "tax_amount": "0.00",
                    "shipping_amount": "0.00",
                    "discount_amount": "0.00",
                    "reference_id": self.name,
                    "items": [
                        {
                            "title": self.sale_order_id.name,
                            "description": _("Sale order advance payment"),
                            "quantity": 1,
                            "unit_price": "%.2f" % self.amount,
                            "discount_amount": "0.00",
                            "reference_id": self.name,
                            "category": "Automotive",
                        }
                    ],
                },
                "order_history": [
                    {
                        "purchased_at": fields.Datetime.now().strftime(
                            "%Y-%m-%dT%H:%M:%SZ"
                        ),
                        "amount": "%.2f" % self.amount,
                        "payment_method": "card",
                        "status": "new",
                        "buyer": {
                            "phone": phone or "",
                            "email": email or "",
                            "name": partner.name or "",
                            "dob": "",
                        },
                        "shipping_address": {
                            "city": partner.city or "city",
                            "address": partner.street or "address",
                            "zip": partner.zip or "zip",
                        },
                    }
                ],
                "shipping_address": {
                    "city": partner.city or "city",
                    "address": partner.street or "address",
                    "zip": partner.zip or "zip",
                },
            },
            "lang": (self.env.context.get("lang") or "en_US")[:2],
            "merchant_code": merchant_code,
            "merchant_urls": {
                "success": "%s?result=success" % callback_url,
                "cancel": "%s?result=cancel" % callback_url,
                "failure": "%s?result=failure" % callback_url,
            },
        }
        try:
            response = requests.post(
                checkout_url,
                json=payload,
                headers=self._tabby_headers(),
                timeout=20,
            )
            response.raise_for_status()
            result = response.json()
            products = result.get("configuration", {}).get("available_products", {})
            installments = products.get("installments") or []
            payment_data = result.get("payment") or {}
            external_reference = payment_data.get("id") or result.get("id")
            web_url = installments[0].get("web_url") if installments else False
            if not external_reference or not web_url:
                raise ValueError(self._tabby_rejection_message(result))
        except (requests.RequestException, ValueError, IndexError, TypeError) as error:
            self.write({"state": "failed", "error_message": str(error)})
            return False
        self.write(
            {
                "state": "pending",
                "external_reference": external_reference,
                "checkout_url": web_url,
                "provider_status": "created",
                "error_message": False,
            }
        )
        return web_url

    def _refresh_tabby_status(self):
        self.ensure_one()
        if not self.external_reference:
            raise UserError(_("The Tabby payment has no external reference."))
        payment_api_url = self._get_config("tabby.payment_api_url")
        if not payment_api_url:
            raise UserError(_("Tabby payment status API URL is not configured."))
        url = "%s/%s" % (payment_api_url.rstrip("/"), self.external_reference)
        try:
            response = requests.get(
                url,
                headers=self._tabby_headers(),
                timeout=20,
            )
            response.raise_for_status()
            result = response.json()
        except (requests.RequestException, ValueError) as error:
            self.error_message = str(error)
            return False
        status = str(result.get("status", "")).lower()
        self.provider_status = status
        if status in ("authorized", "closed", "captured", "paid"):
            self._mark_provider_paid(status)
        elif status in ("rejected", "expired", "cancelled", "failed"):
            self.write(
                {
                    "state": "failed",
                    "error_message": result.get("error")
                    or _("Tabby payment was not approved."),
                }
            )
        else:
            self.state = "pending"
        return self.state

    def _reconcile_available_invoices(self, raise_if_missing=False):
        for allocation in self:
            payment = allocation.account_payment_id
            invoices = allocation.sale_order_id.invoice_ids.filtered(
                lambda move: move.state == "posted"
                and move.move_type == "out_invoice"
                and move.payment_state not in ("paid", "reversed")
            )
            if not payment or not invoices:
                if raise_if_missing:
                    raise UserError(
                        _("No posted unpaid invoice is available for reconciliation.")
                    )
                continue
            payment_lines = payment.sudo().move_id.line_ids.filtered(
                lambda line: line.account_id.account_type == "asset_receivable"
                and not line.reconciled
            )
            invoice_lines = invoices.sudo().line_ids.filtered(
                lambda line: line.account_id.account_type == "asset_receivable"
                and not line.reconciled
            )
            lines = payment_lines | invoice_lines
            if lines:
                lines.reconcile()
