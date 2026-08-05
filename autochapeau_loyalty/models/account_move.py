import logging

from odoo import _, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class AccountMove(models.Model):
    _inherit = "account.move"

    loyalty_points_granted = fields.Float(
        string="Loyalty Points Granted",
        copy=False,
        readonly=True,
        help="Autochapeau loyalty points granted when this invoice was paid.",
    )
    loyalty_earn_done = fields.Boolean(
        string="Loyalty Earn Done",
        copy=False,
        readonly=True,
        help="Loyalty points were already granted for this invoice (any destination).",
    )

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

    def _invoice_paid_hook(self):
        _logger.critical(
            "[autochapeau_loyalty] _invoice_paid_hook called for moves=%s",
            self.mapped("name"),
        )
        res = super()._invoice_paid_hook()
        self._grant_autochapeau_loyalty_points(source="_invoice_paid_hook")
        return res

    def write(self, vals):
        res = super().write(vals)
        # Backup trigger: some payment flows update payment_state without the hook path.
        if vals.get("payment_state") in ("paid", "in_payment"):
            _logger.critical(
                "[autochapeau_loyalty] write(payment_state=%s) on moves=%s",
                vals.get("payment_state"),
                self.mapped("name"),
            )
            self.filtered(
                lambda move: move.move_type == "out_invoice"
                and move.payment_state in ("paid", "in_payment")
            )._grant_autochapeau_loyalty_points(source="write.payment_state")
        return res

    def _grant_autochapeau_loyalty_points(self, source="unknown"):
        _logger.critical(
            "[autochapeau_loyalty] _grant start source=%s moves=%s",
            source,
            [(m.id, m.name, m.move_type, m.state, m.payment_state) for m in self],
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
            if move.payment_state not in ("paid", "in_payment"):
                _logger.critical(
                    "%s skip: payment_state=%s",
                    prefix,
                    move.payment_state,
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

            sale_orders = move.invoice_line_ids.sale_line_ids.order_id
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

    def action_grant_autochapeau_loyalty_points(self):
        """Manual button for already-paid invoices that missed the automatic grant."""
        _logger.critical(
            "[autochapeau_loyalty] manual Grant button on moves=%s",
            self.mapped("name"),
        )
        for move in self:
            if move.move_type != "out_invoice":
                raise UserError(_("Loyalty points can only be granted on customer invoices."))
            if move.state != "posted":
                raise UserError(_("The invoice must be posted."))
            if move.payment_state not in ("paid", "in_payment"):
                raise UserError(_("The invoice must be paid first."))
            if move.loyalty_earn_done or move.loyalty_points_granted:
                raise UserError(_("Loyalty points were already granted on this invoice."))
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
