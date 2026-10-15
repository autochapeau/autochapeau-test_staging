import logging
from datetime import timedelta

from odoo import _, fields, models
from odoo.exceptions import UserError

from .constants import LOYALTY_EARN_DELAY_DAYS

_logger = logging.getLogger(__name__)


class AccountMove(models.Model):
    _inherit = "account.move"

    loyalty_points_granted = fields.Float(
        string="Loyalty Points Granted",
        copy=False,
        readonly=True,
        help="Autochapeau loyalty points granted 7 days after this invoice was confirmed.",
    )
    loyalty_earn_done = fields.Boolean(
        string="Loyalty Earn Done",
        copy=False,
        readonly=True,
        help="Loyalty points were already granted for this invoice (any destination).",
    )
    loyalty_confirm_date = fields.Date(
        string="Loyalty Confirm Date",
        copy=False,
        readonly=True,
        help="Date the customer invoice was posted; loyalty points are granted "
             "%s days later." % LOYALTY_EARN_DELAY_DAYS,
    )

    def action_post(self):
        res = super().action_post()
        today = fields.Date.context_today(self)
        for move in self.filtered(
            lambda m: m.move_type == "out_invoice" and m.state == "posted" and not m.loyalty_confirm_date
        ):
            move.loyalty_confirm_date = today
        return res

    def _get_invoice_loyalty_type(self):
        """Destination chosen on the related SO, else partner preference."""
        self.ensure_one()
        orders = self.invoice_line_ids.sale_line_ids.order_id
        if orders and orders[0].loyalty_type:
            return orders[0].loyalty_type
        partner = self.partner_id.commercial_partner_id
        return partner.preferred_loyalty_type or "autochapeau"

    def _grant_external_loyalty_on_paid(self, loyalty_type, base_amount):
        """Hook implemented by portal_api for Alrajhi / Qitaf earn APIs."""
        self.ensure_one()
        _logger.critical(
            "[autochapeau_loyalty] external earn not implemented locally "
            "type=%s amount=%s move=%s (install/upgrade portal_api)",
            loyalty_type,
            base_amount,
            self.name,
        )
        return False

    def _get_loyalty_amount_before_discount(self):
        """Invoice untaxed amount before line discounts.

        Uses price_unit * qty with taxes.compute_all so price-included VAT
        (common in KSA) is extracted and points are based on tax-excluded amount.
        In Odoo 16+, product lines use display_type='product' (truthy).
        """
        self.ensure_one()
        amount = 0.0
        redeem_product = self.env.ref(
            "autochapeau_loyalty.product_product_loyalty_redeem",
            raise_if_not_found=False,
        )
        for line in self.invoice_line_ids:
            if line.display_type in ("line_section", "line_note"):
                continue
            # Skip loyalty redemption discount lines (do not earn points on them).
            sale_lines = line.sale_line_ids
            if sale_lines and any(sale_lines.mapped("is_loyalty_redeem_line")):
                continue
            if redeem_product and line.product_id == redeem_product:
                continue
            taxes = line.tax_ids
            if taxes:
                # Do not apply line discount: loyalty base is before discount.
                res = taxes.compute_all(
                    line.price_unit,
                    currency=line.currency_id,
                    quantity=line.quantity,
                    product=line.product_id,
                    partner=line.partner_id,
                )
                amount += res.get("total_excluded", 0.0)
            else:
                amount += line.price_unit * line.quantity
        if amount <= 0:
            amount = self.amount_untaxed
            _logger.critical(
                "[autochapeau_loyalty] move=%s used fallback amount_untaxed=%s lines=%s",
                self.name,
                amount,
                [
                    (
                        l.id,
                        l.display_type,
                        l.product_id.display_name,
                        l.price_unit,
                        l.quantity,
                        l.price_subtotal,
                        l.tax_ids.mapped("name"),
                    )
                    for l in self.invoice_line_ids
                ],
            )
        return amount

    def _get_loyalty_confirm_date(self):
        """Date used to compute the 7-day earn delay."""
        self.ensure_one()
        return self.loyalty_confirm_date or self.invoice_date or self.date

    def _is_loyalty_earn_due(self):
        """True when confirm date + delay days is on or before today."""
        self.ensure_one()
        confirm_date = self._get_loyalty_confirm_date()
        if not confirm_date:
            return False
        today = fields.Date.context_today(self)
        return confirm_date <= today - timedelta(days=LOYALTY_EARN_DELAY_DAYS)

    def _cron_grant_autochapeau_loyalty_points(self):
        """Daily job: grant loyalty points on invoices confirmed 7+ days ago."""
        today = fields.Date.context_today(self)
        cutoff = today - timedelta(days=LOYALTY_EARN_DELAY_DAYS)
        candidates = self.search(
            [
                ("move_type", "=", "out_invoice"),
                ("state", "=", "posted"),
                ("loyalty_earn_done", "=", False),
                ("loyalty_points_granted", "=", 0),
            ]
        )
        due = candidates.filtered(
            lambda move: (move._get_loyalty_confirm_date() or False)
            and move._get_loyalty_confirm_date() <= cutoff
        )
        _logger.critical(
            "[autochapeau_loyalty] cron due_count=%s cutoff=%s sample=%s",
            len(due),
            cutoff,
            due[:20].mapped("name"),
        )
        if due:
            due._grant_autochapeau_loyalty_points(source="cron_7_days")
        return True

    def _grant_autochapeau_loyalty_points(self, source="unknown"):
        _logger.critical(
            "[autochapeau_loyalty] _grant start source=%s moves=%s",
            source,
            [(m.id, m.name, m.move_type, m.state, m._get_loyalty_confirm_date()) for m in self],
        )
        for move in self:
            prefix = "[autochapeau_loyalty] move=%s(%s)" % (move.id, move.name or "draft")

            if move.move_type != "out_invoice" or move.state != "posted":
                _logger.critical(
                    "%s skip: move_type=%s state=%s",
                    prefix,
                    move.move_type,
                    move.state,
                )
                continue
            if not move._is_loyalty_earn_due():
                _logger.critical(
                    "%s skip: not due yet confirm_date=%s delay_days=%s",
                    prefix,
                    move._get_loyalty_confirm_date(),
                    LOYALTY_EARN_DELAY_DAYS,
                )
                continue
            if move.loyalty_earn_done or move.loyalty_points_granted:
                _logger.critical(
                    "%s skip: already granted points=%s earn_done=%s",
                    prefix,
                    move.loyalty_points_granted,
                    move.loyalty_earn_done,
                )
                continue

            sale_orders = move.invoice_line_ids.sale_line_ids.order_id
            if sale_orders.filtered(lambda order: order.order_type == "contract"):
                _logger.critical(
                    "%s skip: related Contract sale order(s)=%s",
                    prefix,
                    sale_orders.filtered(lambda order: order.order_type == "contract").mapped("name"),
                )
                continue

            base_amount = move._get_loyalty_amount_before_discount()
            _logger.critical("%s base_amount_before_discount=%s", prefix, base_amount)
            if base_amount <= 0:
                _logger.critical("%s skip: base_amount <= 0", prefix)
                continue

            loyalty_type = move._get_invoice_loyalty_type()
            _logger.critical("%s loyalty_type=%s", prefix, loyalty_type)

            if loyalty_type in ("alrajhi", "qitaf"):
                ok = move._grant_external_loyalty_on_paid(loyalty_type, base_amount)
                if ok:
                    # Mark done using loyalty_points_granted so the form view
                    # (which must stay compatible) can hide the Grant button.
                    move.loyalty_points_granted = base_amount
                    move.loyalty_earn_done = True
                    _logger.critical("%s external earn success type=%s", prefix, loyalty_type)
                else:
                    _logger.critical("%s external earn FAILED type=%s", prefix, loyalty_type)
                continue

            partner = move.partner_id.commercial_partner_id
            _logger.critical(
                "%s partner=%s(%s) membership=%s",
                prefix,
                partner.id,
                partner.display_name,
                partner.membership_id.display_name if partner.membership_id else False,
            )
            points = partner._get_autochapeau_loyalty_points_for_amount(base_amount)
            _logger.critical("%s computed_points=%s", prefix, points)
            if points <= 0:
                _logger.critical("%s skip: computed points <= 0", prefix)
                continue

            card = partner._get_autochapeau_loyalty_card(create_if_missing=True)
            if not card:
                _logger.critical(
                    "%s skip: no loyalty card (program missing? company.loyalty_program_id=%s)",
                    prefix,
                    move.company_id.loyalty_program_id.display_name
                    if hasattr(move.company_id, "loyalty_program_id")
                    else None,
                )
                continue

            old_points = card.points
            card.points += points
            _logger.critical(
                "%s card=%s program=%s points %s -> %s (+%s)",
                prefix,
                card.id,
                card.program_id.display_name,
                old_points,
                card.points,
                points,
            )

            if hasattr(partner, "_compute_loyalty"):
                partner.invalidate_recordset(
                    ["loyalty_card_id", "loyalty_balance", "wallet_card_id", "wallet_balance"]
                )

            order = sale_orders[:1]
            move.loyalty_points_granted = points
            move.loyalty_earn_done = True
            try:
                partner.loyalty_exchange_log_ids = [
                    (
                        0,
                        0,
                        {
                            "type": "loyalty_invoice_earn",
                            "points": points,
                            "amount": base_amount,
                            "card_destination_id": card.id,
                            "order_id": order.id if order else False,
                        },
                    )
                ]
                _logger.critical(
                    "%s success: granted=%s order=%s log created",
                    prefix,
                    points,
                    order.name if order else False,
                )
            except Exception:
                _logger.critical(
                    "%s failed while creating loyalty_exchange_log "
                    "(points were already added on card=%s)",
                    prefix,
                    card.id,
                    exc_info=True,
                )
                raise

    def _reverse_autochapeau_loyalty_points(self):
        for move in self:
            loyalty_type = move._get_invoice_loyalty_type()
            # Only reverse Autochapeau club points; external programs cannot be undone here.
            if (
                move.loyalty_points_granted
                and loyalty_type == "autochapeau"
            ):
                partner = move.partner_id.commercial_partner_id
                card = partner._get_autochapeau_loyalty_card(create_if_missing=False)
                if card:
                    card.points = max(card.points - move.loyalty_points_granted, 0.0)
                    if hasattr(partner, "_compute_loyalty"):
                        partner.invalidate_recordset(
                            ["loyalty_card_id", "loyalty_balance", "wallet_card_id", "wallet_balance"]
                        )
                _logger.critical(
                    "[autochapeau_loyalty] reversed points=%s on move=%s",
                    move.loyalty_points_granted,
                    move.name,
                )
            move.loyalty_points_granted = 0.0
            move.loyalty_earn_done = False
            # Keep loyalty_confirm_date so re-posting can still use the original
            # confirm day; cleared only when moving back to draft then re-posted
            # will refresh if empty — on draft/cancel clear it so a new post
            # starts a fresh 7-day window.
            move.loyalty_confirm_date = False

    def action_grant_autochapeau_loyalty_points(self):
        """Manual button for invoices that reached the 7-day delay but missed the cron."""
        _logger.critical(
            "[autochapeau_loyalty] manual Grant button on moves=%s",
            self.mapped("name"),
        )
        for move in self:
            if move.move_type != "out_invoice":
                raise UserError(_("Loyalty points can only be granted on customer invoices."))
            if move.state != "posted":
                raise UserError(_("The invoice must be posted."))
            if not move._is_loyalty_earn_due():
                confirm_date = move._get_loyalty_confirm_date()
                raise UserError(_(
                    "Loyalty points are granted %(days)s days after invoice confirmation. "
                    "Confirm date: %(date)s."
                ) % {
                    "days": LOYALTY_EARN_DELAY_DAYS,
                    "date": confirm_date or _("(missing)"),
                })
            if move.loyalty_earn_done or move.loyalty_points_granted:
                raise UserError(_("Loyalty points were already granted on this invoice."))
            sale_orders = move.invoice_line_ids.sale_line_ids.order_id
            if sale_orders.filtered(lambda order: order.order_type == "contract"):
                raise UserError(_(
                    "Loyalty points are not granted for Contract sale orders."
                ))
        self._grant_autochapeau_loyalty_points(source="manual_button")
        missing = self.filtered(
            lambda move: not move.loyalty_earn_done and not move.loyalty_points_granted
        )
        if missing:
            raise UserError(
                _(
                    "Could not grant loyalty points. Check destination (Autochapeau / "
                    "Alrajhi / Qitaf), phone number, and server logs for [autochapeau_loyalty]."
                )
            )
        return True

    def button_draft(self):
        self._reverse_autochapeau_loyalty_points()
        return super().button_draft()

    def button_cancel(self):
        self._reverse_autochapeau_loyalty_points()
        return super().button_cancel()
