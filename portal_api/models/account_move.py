# -*- coding: utf-8 -*-
import logging

from odoo import models

_logger = logging.getLogger(__name__)


class AccountMove(models.Model):
    _inherit = "account.move"

    def _grant_external_loyalty_on_paid(self, loyalty_type, base_amount):
        """Earn Alrajhi / Qitaf points when the invoice is paid."""
        self.ensure_one()
        partner = self.partner_id.commercial_partner_id
        phone = partner.phone or partner.mobile
        orders = self.invoice_line_ids.sale_line_ids.order_id
        order = orders[:1]
        branch = (
            order.appointment_id.company_id
            if order and order.appointment_id
            else self.company_id
        )
        branch_code = getattr(branch, "branch_code", False) or False
        service = self.env["loyalty.earn.service"]

        if loyalty_type == "alrajhi":
            result = service.earn_alrajhi(phone, base_amount, branch_code=branch_code)
            log_type = "loyalty_alrajhi_earn"
        elif loyalty_type == "qitaf":
            result = service.earn_qitaf(phone, base_amount)
            log_type = "loyalty_qitaf_earn"
        else:
            return False

        _logger.critical(
            "[autochapeau_loyalty] external earn move=%s type=%s amount=%s phone=%s result=%s",
            self.name,
            loyalty_type,
            base_amount,
            phone,
            result.get("success"),
        )
        if not result.get("success"):
            _logger.critical(
                "[autochapeau_loyalty] external earn failed: %s",
                result.get("message"),
            )
            return False

        partner.loyalty_exchange_log_ids = [
            (
                0,
                0,
                {
                    "type": log_type,
                    "points": base_amount,
                    "amount": base_amount,
                    "order_id": order.id if order else False,
                },
            )
        ]
        return True
