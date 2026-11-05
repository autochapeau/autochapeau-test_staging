from odoo import _, api, Command, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError


class AccountJournal(models.Model):
    _inherit = "account.journal"

    collection_fee_enabled = fields.Boolean(string="Deduct Collection Fees")
    collection_fee_percent = fields.Float(string="Collection Fee %", digits=(16, 4))
    collection_fee_tax_percent = fields.Float(string="Tax on Fee %", digits=(16, 4), default=15)
    collection_fee_account_id = fields.Many2one("account.account", string="Collection Fee Account", check_company=True)
    collection_fee_tax_account_id = fields.Many2one("account.account", string="Fee Tax Account", check_company=True)

    @api.constrains("collection_fee_enabled", "collection_fee_percent", "collection_fee_tax_percent",
                    "collection_fee_account_id", "collection_fee_tax_account_id", "type", "default_account_id")
    def _check_collection_fees(self):
        for journal in self:
            if not journal.collection_fee_enabled:
                continue
            if journal.type not in ("bank", "cash"):
                raise ValidationError(_("Collection fees are only available on bank and cash journals."))
            if not (0 < journal.collection_fee_percent < 100 and 0 <= journal.collection_fee_tax_percent <= 100):
                raise ValidationError(_("Use a positive fee below 100% and a tax rate between 0 and 100%."))
            if journal.collection_fee_percent * (1 + journal.collection_fee_tax_percent / 100) >= 100:
                raise ValidationError(_("The fee and its tax must leave a positive net collection."))
            if not journal.collection_fee_account_id or (journal.collection_fee_tax_percent and not journal.collection_fee_tax_account_id):
                raise ValidationError(_("Configure the fee account and, when applicable, the fee tax account."))
            accounts = journal.collection_fee_account_id | journal.collection_fee_tax_account_id
            if (accounts & journal.default_account_id) or accounts.filtered(
                lambda account: account.deprecated or account.account_type in ("asset_receivable", "liability_payable", "asset_cash")
            ):
                raise ValidationError(_("Fee accounts must be active accounts separate from bank, cash and customer/vendor control accounts."))
            if journal.collection_fee_tax_percent and journal.collection_fee_account_id == journal.collection_fee_tax_account_id:
                raise ValidationError(_("Select separate accounts for the fee and its tax."))


class AccountMoveLine(models.Model):
    _inherit = "account.move.line"

    collection_charge_kind = fields.Selection([("fee", "Collection Fee"), ("tax", "Tax on Collection Fee")], copy=False, readonly=True)


class AccountPayment(models.Model):
    _inherit = "account.payment"

    collection_fee_percent = fields.Float(readonly=True, copy=False, digits=(16, 4))
    collection_fee_tax_percent = fields.Float(readonly=True, copy=False, digits=(16, 4))
    collection_fee_account_id = fields.Many2one("account.account", readonly=True, copy=False, check_company=True)
    collection_fee_tax_account_id = fields.Many2one("account.account", readonly=True, copy=False, check_company=True)
    collection_fee_amount = fields.Monetary(compute="_compute_collection_amounts")
    collection_fee_tax_amount = fields.Monetary(compute="_compute_collection_amounts")
    collection_net_amount = fields.Monetary(compute="_compute_collection_amounts", string="Net Bank/Cash Amount")
    transfer_proof_ids = fields.Many2many("ir.attachment", "payment_transfer_proof_rel", "payment_id", "attachment_id",
                                        string="Transfer Proof", copy=True)
    transfer_proof_required = fields.Boolean(compute="_compute_transfer_proof_required")

    _collection_snapshot_fields = {"collection_fee_percent", "collection_fee_tax_percent",
                                   "collection_fee_account_id", "collection_fee_tax_account_id"}

    @api.depends("journal_id.type")
    def _compute_transfer_proof_required(self):
        for payment in self:
            payment.transfer_proof_required = payment.journal_id.type == "bank"

    @api.depends("amount", "currency_id", "collection_fee_percent", "collection_fee_tax_percent")
    def _compute_collection_amounts(self):
        for payment in self:
            currency = payment.currency_id or payment.company_id.currency_id
            fee = currency.round(payment.amount * payment.collection_fee_percent / 100)
            tax = currency.round(fee * payment.collection_fee_tax_percent / 100)
            payment.collection_fee_amount = fee
            payment.collection_fee_tax_amount = tax
            payment.collection_net_amount = payment.amount - fee - tax

    @api.model
    def _collection_snapshot_values(self, journal, values):
        enabled = (journal.collection_fee_enabled and values.get("payment_type", "inbound") == "inbound"
                   and values.get("partner_type", "customer") == "customer" and not values.get("is_internal_transfer")
                   and not values.get("destination_journal_id"))
        return {
            "collection_fee_percent": journal.collection_fee_percent if enabled else 0,
            "collection_fee_tax_percent": journal.collection_fee_tax_percent if enabled else 0,
            "collection_fee_account_id": journal.collection_fee_account_id.id if enabled else False,
            "collection_fee_tax_account_id": journal.collection_fee_tax_account_id.id if enabled else False,
        }

    @api.model_create_multi
    def create(self, vals_list):
        prepared = []
        for values in vals_list:
            values = dict(values)
            journal = self.env["account.journal"].browse(values.get("journal_id"))
            if not journal:
                journal = self.move_id.with_context(is_payment=True)._search_default_journal()
                values["journal_id"] = journal.id
            values.update(self._collection_snapshot_values(journal, values))
            prepared.append(values)
        payments = super().create(prepared)
        payments._own_transfer_proofs()
        return payments

    def _own_transfer_proofs(self):
        for payment in self:
            owned = self.env["ir.attachment"]
            for attachment in payment.transfer_proof_ids:
                attachment.check("read")
                if attachment.type != "binary" or not attachment.file_size:
                    raise ValidationError(_("Transfer proof must be a non-empty uploaded file."))
                if attachment.res_model == self._name and attachment.res_id == payment.id:
                    owned |= attachment
                else:
                    owned |= attachment.copy({"res_model": self._name, "res_id": payment.id,
                                               "public": False, "access_token": False})
            if owned != payment.transfer_proof_ids:
                super(AccountPayment, payment).write({"transfer_proof_ids": [Command.set(owned.ids)]})

    def _check_transfer_proof(self):
        for payment in self.filtered("transfer_proof_required"):
            proofs = payment.transfer_proof_ids | self.env["ir.attachment"].search([
                ("res_model", "in", ["account.payment", "account.move"]),
                ("type", "=", "binary"), ("file_size", ">", 0),
                "|", "&", ("res_model", "=", "account.payment"), ("res_id", "=", payment.id),
                "&", ("res_model", "=", "account.move"), ("res_id", "=", payment.move_id.id),
            ])
            if not proofs:
                raise UserError(_("Upload transfer proof before confirming a bank payment."))
            proofs.check("read")

    def _lock_collection_proofs(self):
        if self.ids:
            # Updating the row version also makes a concurrent post/proof edit
            # retry under PostgreSQL's repeatable-read isolation.
            self.env.cr.execute("SELECT id FROM account_payment WHERE id IN %s ORDER BY id FOR UPDATE", [tuple(self.ids)])
            self.env.cr.execute(
                "UPDATE account_payment SET write_date=write_date WHERE id IN %s",
                [tuple(sorted(self.ids))],
            )
            self.invalidate_recordset(["state", "transfer_proof_ids"])

    def _sync_collection_allocations(self):
        for payment in self:
            allocations = self.env["sale.order.payment"].sudo().search([("account_payment_id", "=", payment.id)])
            if payment.state == "posted":
                allocations.filtered(lambda allocation: allocation.state in ("needs_review", "processing", "pending")).write({
                    "state": "paid", "error_message": False,
                })
            elif payment.state == "draft":
                allocations.filtered(lambda allocation: allocation.state in ("paid", "cancelled")).write({
                    "state": "needs_review", "error_message": _("The linked customer payment is in draft. Review and repost it."),
                })
            elif payment.state == "cancel":
                allocations.filtered(lambda allocation: allocation.state != "cancelled").write({"state": "cancelled"})

    def _check_collection_fee_lines(self):
        for payment in self.filtered("collection_fee_account_id"):
            liquidity, counterpart, writeoffs = payment._seek_for_lines()
            currency = payment.currency_id
            if len(liquidity) != 1 or len(counterpart) != 1 or currency.compare_amounts(
                liquidity.amount_currency, payment.collection_net_amount
            ):
                raise ValidationError(_("The payment entry does not match its net collection amount."))
            for kind, amount, account in (("fee", payment.collection_fee_amount, payment.collection_fee_account_id),
                                          ("tax", payment.collection_fee_tax_amount, payment.collection_fee_tax_account_id)):
                lines = writeoffs.filtered(lambda line: line.collection_charge_kind == kind)
                if currency.is_zero(amount):
                    if lines:
                        raise ValidationError(_("Unexpected fee lines exist on this payment."))
                elif len(lines) != 1 or lines.account_id != account or currency.compare_amounts(lines.amount_currency, amount):
                    raise ValidationError(_("The payment fee lines do not match its saved fee configuration."))

    def write(self, vals):
        if self._collection_snapshot_fields.intersection(vals):
            raise AccessError(_("Collection fee snapshots are set from the journal and cannot be edited directly."))
        if "transfer_proof_ids" in vals:
            self._lock_collection_proofs()
            if self.filtered(lambda payment: payment.state != "draft"):
                raise UserError(_("Transfer proof can only be changed while the payment is in draft."))
        financial = set(self._get_trigger_fields_to_synchronize()) - {"payment_reference"} - self._collection_snapshot_fields
        for payment in self.filtered(lambda pay: pay.state != "draft" and pay.collection_fee_account_id):
            for name in financial.intersection(vals):
                old, new = payment[name], vals[name]
                if payment._fields[name].type == "many2one":
                    old = old.id
                elif payment._fields[name].type == "date":
                    new = fields.Date.to_date(new)
                if old != new:
                    raise UserError(_("Reset a collection payment to draft before changing its financial details."))
        if {"journal_id", "payment_type", "partner_type", "is_internal_transfer"}.intersection(vals):
            for payment in self:
                values = dict(vals)
                journal = self.env["account.journal"].browse(vals.get("journal_id", payment.journal_id.id))
                config = {key: vals.get(key, payment[key]) for key in ("payment_type", "partner_type", "is_internal_transfer")}
                changed = journal != payment.journal_id or any(config[key] != payment[key] for key in config)
                if changed:
                    values.update(payment._collection_snapshot_values(journal, config))
                super(AccountPayment, payment).write(values)
            result = True
        else:
            result = super().write(vals)
        if "transfer_proof_ids" in vals:
            self._own_transfer_proofs()
        return result

    @api.model
    def _get_trigger_fields_to_synchronize(self):
        return super()._get_trigger_fields_to_synchronize() + tuple(self._collection_snapshot_fields)

    def _prepare_move_line_default_vals(self, write_off_line_vals=None, force_balance=None):
        values = super()._prepare_move_line_default_vals(write_off_line_vals, force_balance)
        if not self.collection_fee_account_id:
            return values
        if (self.collection_fee_account_id | self.collection_fee_tax_account_id) & self._get_valid_liquidity_accounts():
            raise ValidationError(_("Fee accounts must differ from the payment's bank/outstanding account."))
        currency = self.currency_id
        fee, tax = self.collection_fee_amount, self.collection_fee_tax_amount
        if currency.compare_amounts(self.collection_net_amount, 0) <= 0:
            raise ValidationError(_("The rounded fee and tax must leave a positive net payment."))
        total_balance = 0
        for kind, amount, account in (("fee", fee, self.collection_fee_account_id),
                                       ("tax", tax, self.collection_fee_tax_account_id)):
            if currency.is_zero(amount):
                continue
            balance = currency._convert(amount, self.company_id.currency_id, self.company_id, self.date)
            total_balance += balance
            values.append({"name": _("Collection Fee") if kind == "fee" else _("Tax on Collection Fee"),
                           "account_id": account.id, "partner_id": self.partner_id.id,
                           "currency_id": currency.id, "amount_currency": amount,
                           "debit": max(balance, 0), "credit": max(-balance, 0),
                           "collection_charge_kind": kind})
        liquidity_balance = values[0]["debit"] - values[0]["credit"] - total_balance
        values[0].update(amount_currency=values[0]["amount_currency"] - fee - tax,
                         debit=max(liquidity_balance, 0), credit=max(-liquidity_balance, 0))
        return values

    def _synchronize_to_moves(self, changed_fields):
        if self.env.context.get("skip_account_move_synchronization"):
            return
        charged = self.filtered(lambda pay: pay.collection_fee_account_id or pay.move_id.line_ids.filtered("collection_charge_kind"))
        super(AccountPayment, self - charged)._synchronize_to_moves(changed_fields)
        if not set(changed_fields).intersection(self._get_trigger_fields_to_synchronize()):
            return
        for payment in charged.with_context(skip_account_move_synchronization=True):
            liquidity, counterpart, writeoffs = payment._seek_for_lines()
            if payment.state != "draft":
                if "payment_reference" in changed_fields:
                    values = payment._prepare_move_line_default_vals()
                    liquidity.write({"name": values[0]["name"]})
                    counterpart.write({"name": values[1]["name"]})
                continue
            non_fee = writeoffs.filtered(lambda line: not line.collection_charge_kind)
            extras = [{"name": line.name, "account_id": line.account_id.id, "partner_id": line.partner_id.id,
                       "currency_id": line.currency_id.id, "amount_currency": line.amount_currency, "balance": line.balance}
                      for line in non_fee]
            values = payment._prepare_move_line_default_vals(extras)
            commands = [Command.update(liquidity.id, values[0]) if liquidity else Command.create(values[0]),
                        Command.update(counterpart.id, values[1]) if counterpart else Command.create(values[1])]
            commands += [Command.delete(line.id) for line in writeoffs]
            commands += [Command.create(value) for value in values[2:]]
            payment.move_id.with_context(skip_invoice_sync=True).write({
                "partner_id": payment.partner_id.id, "currency_id": payment.currency_id.id,
                "partner_bank_id": payment.partner_bank_id.id, "line_ids": commands,
            })

    def _synchronize_from_moves(self, changed_fields):
        if self.env.context.get("skip_account_move_synchronization"):
            return
        charged = self.filtered("collection_fee_account_id")
        super(AccountPayment, self - charged)._synchronize_from_moves(changed_fields)
        for payment in charged.with_context(skip_account_move_synchronization=True):
            if payment.move_id.statement_line_id:
                continue
            if "journal_id" in changed_fields and payment.journal_id.type not in ("bank", "cash"):
                raise UserError(_("A payment must belong to a bank or cash journal."))
            if "line_ids" not in changed_fields:
                continue
            liquidity, counterpart, writeoffs = payment._seek_for_lines()
            all_lines = payment.move_id.line_ids
            if len(liquidity) != 1 or len(counterpart) != 1:
                raise UserError(_("A collection payment must have one bank/outstanding line and one customer/vendor line."))
            if any(line.currency_id != all_lines[0].currency_id or line.partner_id != all_lines[0].partner_id for line in all_lines):
                raise UserError(_("All payment lines must use the same currency and partner."))
            gross = liquidity.amount_currency + sum(writeoffs.filtered("collection_charge_kind").mapped("amount_currency"))
            payment.move_id.write({"currency_id": liquidity.currency_id.id, "partner_id": liquidity.partner_id.id})
            payment.write({"amount": abs(gross), "currency_id": liquidity.currency_id.id,
                           "partner_id": liquidity.partner_id.id, "destination_account_id": counterpart.account_id.id})

    @api.depends("amount", "payment_type", "move_id.line_ids.balance", "move_id.line_ids.collection_charge_kind")
    def _compute_amount_company_currency_signed(self):
        super()._compute_amount_company_currency_signed()
        for payment in self.filtered("collection_fee_account_id"):
            liquidity, _counterpart, writeoffs = payment._seek_for_lines()
            payment.amount_company_currency_signed = sum(
                (liquidity | writeoffs.filtered("collection_charge_kind")).mapped("balance")
            )


class AccountMove(models.Model):
    _inherit = "account.move"

    def _post(self, soft=True):
        self.payment_id._lock_collection_proofs()
        self.payment_id._check_transfer_proof()
        self.payment_id._check_collection_fee_lines()
        return super()._post(soft=soft)


class Attachment(models.Model):
    _inherit = "ir.attachment"

    def _check_posted_transfer_proof(self):
        payments = self.env["account.payment"].sudo().search([
            ("journal_id.type", "=", "bank"),
            ("transfer_proof_ids", "in", self.ids),
        ])
        for attachment in self:
            if attachment.res_model == "account.payment":
                payments |= self.env["account.payment"].sudo().browse(attachment.res_id).exists().filtered(
                    lambda pay: pay.journal_id.type == "bank")
            elif attachment.res_model == "account.move":
                payments |= self.env["account.move"].sudo().browse(attachment.res_id).exists().payment_id.filtered(
                    lambda pay: pay.journal_id.type == "bank")
        payments._lock_collection_proofs()
        if payments.filtered(lambda pay: pay.state == "posted"):
            raise UserError(_("Proof for a posted bank payment cannot be removed or replaced. Reset the payment to draft first."))

    def unlink(self):
        self._check_posted_transfer_proof()
        return super().unlink()

    def write(self, vals):
        if {"datas", "raw", "res_model", "res_id", "type", "url"}.intersection(vals):
            self._check_posted_transfer_proof()
        return super().write(vals)
