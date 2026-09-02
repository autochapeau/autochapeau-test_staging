from dateutil.relativedelta import relativedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools import float_round


class AccountMove(models.Model):
    _inherit = "account.move"

    deferred_move_ids = fields.One2many(
        "account.move",
        "deferred_original_move_id",
        string="Deferred Entries",
        copy=False,
    )
    deferred_original_move_id = fields.Many2one(
        "account.move",
        string="Original Deferred Invoice",
        copy=False,
        index=True,
        ondelete="cascade",
    )
    deferred_entry_count = fields.Integer(
        compute="_compute_deferred_entry_count",
    )

    @api.depends("deferred_move_ids")
    def _compute_deferred_entry_count(self):
        for move in self:
            move.deferred_entry_count = len(move.deferred_move_ids)

    def action_post(self):
        res = super().action_post()
        self._generate_deferred_revenue_entries()
        return res

    def button_draft(self):
        self._unlink_deferred_revenue_entries()
        return super().button_draft()

    def button_cancel(self):
        self._unlink_deferred_revenue_entries()
        return super().button_cancel()

    def action_view_deferred_entries(self):
        self.ensure_one()
        return {
            "name": _("Deferred Entries"),
            "type": "ir.actions.act_window",
            "res_model": "account.move",
            "view_mode": "tree,form",
            "domain": [("id", "in", self.deferred_move_ids.ids)],
            "context": {"default_move_type": "entry"},
        }

    def _unlink_deferred_revenue_entries(self):
        deferred_moves = self.mapped("deferred_move_ids")
        if not deferred_moves:
            return
        deferred_moves.filtered(lambda m: m.state == "posted").button_draft()
        deferred_moves.with_context(force_delete=True).unlink()

    def _is_deferred_purchase_move(self):
        self.ensure_one()
        return self.move_type in ("in_invoice", "in_refund")

    def _is_deferred_refund_move(self):
        self.ensure_one()
        return self.move_type in ("out_refund", "in_refund")

    def _generate_deferred_revenue_entries(self):
        for move in self:
            if move.move_type not in (
                "out_invoice",
                "out_refund",
                "in_invoice",
                "in_refund",
            ):
                continue
            if move.deferred_move_ids:
                continue
            deferred_lines = move.invoice_line_ids.filtered(
                lambda line: line._is_deferred_revenue_line()
            )
            if not deferred_lines:
                continue
            move._create_deferred_revenue_entries(deferred_lines)

    def _get_deferred_revenue_setup(self):
        self.ensure_one()
        company = self.company_id
        journal = company.deferred_revenue_journal_id
        if self._is_deferred_purchase_move():
            account = company.deferred_expense_account_id
            if not journal or not account:
                raise UserError(
                    _(
                        "Please configure the Deferred Journal and Deferred Expense "
                        "Account in Accounting > Configuration > Settings before "
                        "posting vendor bills with deferred dates."
                    )
                )
        else:
            account = company.deferred_revenue_account_id
            if not journal or not account:
                raise UserError(
                    _(
                        "Please configure the Deferred Journal and Deferred Revenue "
                        "Account in Accounting > Configuration > Settings before "
                        "posting invoices with deferred dates."
                    )
                )
        return journal, account

    def _deferred_transfer_debit_on_balance_sheet(self):
        """Whether the balance-sheet (deferred) account is debited on transfer.

        Customer invoice: credit deferred liability (False).
        Vendor bill: debit prepaid asset (True).
        Refunds flip the direction.
        """
        self.ensure_one()
        debit_on_bs = self._is_deferred_purchase_move()
        if self._is_deferred_refund_move():
            debit_on_bs = not debit_on_bs
        return debit_on_bs

    def _create_deferred_revenue_entries(self, deferred_lines):
        self.ensure_one()
        journal, deferred_account = self._get_deferred_revenue_setup()
        today = fields.Date.context_today(self)
        debit_deferred_on_transfer = self._deferred_transfer_debit_on_balance_sheet()
        is_purchase = self._is_deferred_purchase_move()
        Move = self.env["account.move"]
        created_moves = Move

        for line in deferred_lines:
            periods = self._get_equal_month_periods(
                line.deferred_start_date, line.deferred_end_date
            )
            if not periods:
                continue

            pl_account = line.account_id
            if not pl_account:
                raise UserError(
                    _("Invoice line '%s' has no account.") % line.display_name
                )

            total = abs(line.balance)
            amounts = self._split_amount_equally(total, len(periods))

            # 1) Transfer full amount between P&L and deferred balance-sheet account
            if debit_deferred_on_transfer:
                transfer_lines = [
                    (
                        0,
                        0,
                        {
                            "name": _("Deferred transfer - %s") % (line.name or "/"),
                            "account_id": deferred_account.id,
                            "debit": total,
                            "credit": 0.0,
                            "partner_id": self.partner_id.id,
                        },
                    ),
                    (
                        0,
                        0,
                        {
                            "name": _("Deferred transfer - %s") % (line.name or "/"),
                            "account_id": pl_account.id,
                            "debit": 0.0,
                            "credit": total,
                            "partner_id": self.partner_id.id,
                        },
                    ),
                ]
            else:
                transfer_lines = [
                    (
                        0,
                        0,
                        {
                            "name": _("Deferred transfer - %s") % (line.name or "/"),
                            "account_id": pl_account.id,
                            "debit": total,
                            "credit": 0.0,
                            "partner_id": self.partner_id.id,
                        },
                    ),
                    (
                        0,
                        0,
                        {
                            "name": _("Deferred transfer - %s") % (line.name or "/"),
                            "account_id": deferred_account.id,
                            "debit": 0.0,
                            "credit": total,
                            "partner_id": self.partner_id.id,
                        },
                    ),
                ]

            transfer_move = Move.create(
                {
                    "ref": _("Deferral transfer: %s") % (self.name or self.id),
                    "date": self.date,
                    "journal_id": journal.id,
                    "company_id": self.company_id.id,
                    "move_type": "entry",
                    "deferred_original_move_id": self.id,
                    "line_ids": transfer_lines,
                }
            )
            created_moves |= transfer_move

            # 2) Monthly recognition entries (opposite of transfer)
            recognition_label = (
                _("Expense recognition %s: %s")
                if is_purchase
                else _("Revenue recognition %s: %s")
            )
            for period_date, amount in zip(periods, amounts):
                if not amount:
                    continue
                if debit_deferred_on_transfer:
                    # Recognition: credit deferred asset, debit expense
                    recognition_lines = [
                        (
                            0,
                            0,
                            {
                                "name": _("Recognize - %s") % (line.name or "/"),
                                "account_id": pl_account.id,
                                "debit": amount,
                                "credit": 0.0,
                                "partner_id": self.partner_id.id,
                            },
                        ),
                        (
                            0,
                            0,
                            {
                                "name": _("Recognize - %s") % (line.name or "/"),
                                "account_id": deferred_account.id,
                                "debit": 0.0,
                                "credit": amount,
                                "partner_id": self.partner_id.id,
                            },
                        ),
                    ]
                else:
                    # Recognition: debit deferred liability, credit income
                    recognition_lines = [
                        (
                            0,
                            0,
                            {
                                "name": _("Recognize - %s") % (line.name or "/"),
                                "account_id": deferred_account.id,
                                "debit": amount,
                                "credit": 0.0,
                                "partner_id": self.partner_id.id,
                            },
                        ),
                        (
                            0,
                            0,
                            {
                                "name": _("Recognize - %s") % (line.name or "/"),
                                "account_id": pl_account.id,
                                "debit": 0.0,
                                "credit": amount,
                                "partner_id": self.partner_id.id,
                            },
                        ),
                    ]

                recognition = Move.create(
                    {
                        "ref": recognition_label
                        % (period_date.strftime("%Y-%m"), self.name or self.id),
                        "date": period_date,
                        "journal_id": journal.id,
                        "company_id": self.company_id.id,
                        "move_type": "entry",
                        "deferred_original_move_id": self.id,
                        "line_ids": recognition_lines,
                    }
                )
                created_moves |= recognition

        # Post entries that are due; keep future ones in draft
        to_post = created_moves.filtered(lambda m: m.date <= today)
        if to_post:
            to_post.action_post()

    def _get_equal_month_periods(self, start_date, end_date):
        """Return one recognition date per month in the period.

        First period uses the start date; following periods use the 1st of the month.
        """
        if not start_date or not end_date or end_date < start_date:
            return []

        periods = [start_date]
        cursor = start_date.replace(day=1) + relativedelta(months=1)
        last_month = end_date.replace(day=1)
        while cursor <= last_month:
            periods.append(cursor)
            cursor += relativedelta(months=1)
        return periods

    def _split_amount_equally(self, total, count):
        if count <= 0:
            return []
        rounding = self.company_currency_id.rounding or 0.01
        base = float_round(total / count, precision_rounding=rounding)
        amounts = [base] * count
        amounts[-1] = float_round(
            total - sum(amounts[:-1]),
            precision_rounding=rounding,
        )
        return amounts

    @api.model
    def _cron_post_due_deferred_revenue_entries(self):
        today = fields.Date.context_today(self)
        due_moves = self.search(
            [
                ("deferred_original_move_id", "!=", False),
                ("state", "=", "draft"),
                ("date", "<=", today),
            ]
        )
        if due_moves:
            due_moves.action_post()
