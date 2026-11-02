from collections import defaultdict

from odoo import api, fields, models, _, Command
from odoo.exceptions import AccessError, ValidationError, UserError


_BOOKING_TOKEN = object()


class Company(models.Model):
    _inherit = 'res.company'

    commission_accrual_enabled = fields.Boolean(string='Automatically accrue sales commissions', groups='account.group_account_manager')
    commission_journal_id = fields.Many2one('account.journal', string='Commission journal', check_company=True, groups='account.group_account_manager')
    commission_debit_account_id = fields.Many2one('account.account', string='Commission expense (Debit)', check_company=True, groups='account.group_account_manager')
    commission_credit_account_id = fields.Many2one('account.account', string='Commission payable (Credit)', check_company=True, groups='account.group_account_manager')

    @api.constrains('commission_accrual_enabled', 'commission_journal_id', 'commission_debit_account_id', 'commission_credit_account_id')
    def _check_commission_accounting(self):
        for company in self:
            if not company.commission_accrual_enabled:
                continue
            journal, debit, credit = company.commission_journal_id, company.commission_debit_account_id, company.commission_credit_account_id
            if not journal or not debit or not credit:
                raise ValidationError(_('Set the commission journal, debit account and credit account before enabling accruals.'))
            if journal.company_id != company or journal.type != 'general' or not journal.active or journal.currency_id not in (company.currency_id, self.env['res.currency']):
                raise ValidationError(_('Use an active miscellaneous journal in the same company and company currency.'))
            if debit == credit or any(a.company_id != company or a.deprecated or (a.currency_id and a.currency_id != company.currency_id) for a in debit | credit):
                raise ValidationError(_('Use two different, active accounts belonging to this company in company currency.'))
            if not debit.account_type.startswith('expense') or not credit.account_type.startswith('liability'):
                raise ValidationError(_('The debit account must be an expense and the credit account must be a liability/payable account.'))


class Settings(models.TransientModel):
    _inherit = 'res.config.settings'

    commission_accrual_enabled = fields.Boolean(related='company_id.commission_accrual_enabled', readonly=False)
    commission_journal_id = fields.Many2one(related='company_id.commission_journal_id', readonly=False)
    commission_debit_account_id = fields.Many2one(related='company_id.commission_debit_account_id', readonly=False)
    commission_credit_account_id = fields.Many2one(related='company_id.commission_credit_account_id', readonly=False)


class Entry(models.Model):
    _inherit = 'sales.commission.entry'

    accrual_move_id = fields.Many2one('account.move', string='Accrual journal entry', readonly=True, copy=False, ondelete='restrict')
    accounting_status = fields.Selection([('review', 'Needs review'), ('zero', 'Zero commission'), ('pending', 'Not booked'), ('posted', 'Accrued')], compute='_compute_accounting_status')

    @api.depends('status', 'amount', 'accrual_move_id.state')
    def _compute_accounting_status(self):
        for entry in self:
            entry.accounting_status = 'review' if entry.status == 'review' else 'zero' if entry.currency_id.is_zero(entry.amount) else 'posted' if entry.accrual_move_id.sudo().state == 'posted' else 'pending'

    def action_accrue(self):
        if not self.env.user.has_group('account.group_account_manager') or not self.env.user.has_group('sales_region_commission.group_admin'):
            raise AccessError(_('Both Accounting Administrator and Commission Administrator access are required to book historical commissions.'))
        self.check_access_rights('read')
        self.check_access_rule('read')
        for entry in self.sudo().filtered(lambda e: e.accounting_status == 'pending'):
            if entry.move_id.move_type == 'out_refund' and not entry.origin_id.accrual_move_id:
                raise UserError(_('Book the original invoice commission before its credit note.'))
            if entry.move_id.move_type != 'out_refund' and not entry.company_id.commission_accrual_enabled:
                raise UserError(_('Enable commission accruals in Accounting settings first.'))
        self._accrue_commissions()
        return True

    def _accrue_commissions(self):
        entries = self.sudo()
        orders = entries.move_id.sorted('id')
        for invoice in orders:
            self.env.cr.execute('SELECT id FROM account_move WHERE id = %s FOR UPDATE', (invoice.id,))
        entries.invalidate_recordset(['accrual_move_id'])
        buckets = defaultdict(lambda: self.env['sales.commission.entry'])
        for entry in entries.filtered(lambda e: e.status == 'earned' and not e.accrual_move_id and e.move_id.state == 'posted' and not e.currency_id.is_zero(e.amount)):
            company = entry.company_id
            if entry.move_id.move_type == 'out_refund':
                origin_move = entry.origin_id.accrual_move_id
                # Never reverse a liability which has not been recognized.
                if not origin_move:
                    continue
                journal, debit, credit = origin_move.journal_id, origin_move.commission_debit_snapshot_id, origin_move.commission_credit_snapshot_id
            else:
                if not company.commission_accrual_enabled:
                    continue
                company._check_commission_accounting()
                journal, debit, credit = company.commission_journal_id, company.commission_debit_account_id, company.commission_credit_account_id
            buckets[(entry.move_id.id, journal.id, debit.id, credit.id)] |= entry
        Move = self.env['account.move'].sudo().with_context(commission_booking_token=_BOOKING_TOKEN)
        for (invoice_id, journal_id, debit_id, credit_id), lines in buckets.items():
            invoice = self.env['account.move'].sudo().browse(invoice_id)
            commands = []
            for entry in lines:
                amount = entry.amount
                label = _('Commission: %(invoice)s / %(salesperson)s', invoice=invoice.name, salesperson=entry.user_id.name)
                for account_id, balance in ((debit_id, amount), (credit_id, -amount)):
                    account = self.env['account.account'].sudo().browse(account_id)
                    commands.append(Command.create({'name': label, 'account_id': account_id, 'partner_id': entry.user_id.partner_id.id,
                                                    'debit': max(balance, 0), 'credit': max(-balance, 0), 'tax_ids': [Command.clear()],
                                                    'date_maturity': invoice.date if account.account_type == 'liability_payable' else False}))
            accrual = Move.with_company(invoice.company_id).create({
                'move_type': 'entry', 'company_id': invoice.company_id.id, 'journal_id': journal_id, 'date': invoice.date,
                'ref': _('Sales commission accrual: %s') % invoice.name,
                'commission_source_invoice_id': invoice.id, 'commission_debit_snapshot_id': debit_id,
                'commission_credit_snapshot_id': credit_id, 'line_ids': commands,
            })
            accrual.action_post()
            lines.sudo().write({'accrual_move_id': accrual.id})


class Move(models.Model):
    _inherit = 'account.move'

    commission_source_invoice_id = fields.Many2one('account.move', readonly=True, copy=False, ondelete='restrict', index=True)
    commission_debit_snapshot_id = fields.Many2one('account.account', readonly=True, copy=False, ondelete='restrict')
    commission_credit_snapshot_id = fields.Many2one('account.account', readonly=True, copy=False, ondelete='restrict')
    commission_reversed_by_id = fields.Many2one('account.move', readonly=True, copy=False, ondelete='restrict')
    commission_is_reversal = fields.Boolean(readonly=True, copy=False)
    commission_account_move_ids = fields.One2many('account.move', 'commission_source_invoice_id', string='Commission accounting entries')

    @api.model_create_multi
    def create(self, vals_list):
        protected = {'commission_source_invoice_id', 'commission_debit_snapshot_id', 'commission_credit_snapshot_id', 'commission_reversed_by_id', 'commission_is_reversal'}
        if any(protected & v.keys() for v in vals_list) and self.env.context.get('commission_booking_token') is not _BOOKING_TOKEN:
            raise AccessError(_('Commission journal links are managed by the accrual process.'))
        return super().create(vals_list)

    def write(self, vals):
        protected = {'commission_source_invoice_id', 'commission_debit_snapshot_id', 'commission_credit_snapshot_id', 'commission_reversed_by_id', 'commission_is_reversal'}
        internal = self.env.context.get('commission_booking_token') is _BOOKING_TOKEN
        if protected & vals.keys() and not internal:
            raise AccessError(_('Commission journal links are managed by the accrual process.'))
        if not internal and {'state', 'line_ids', 'journal_id', 'date', 'company_id', 'currency_id'} & vals.keys() and self.filtered('commission_source_invoice_id'):
            raise UserError(_('Commission journal entries are managed through their source invoice.'))
        return super().write(vals)

    def _post(self, soft=True):
        posted = super()._post(soft=soft)
        self.env['sales.commission.entry'].sudo().search([('move_id', 'in', posted.filtered(lambda m: m.move_type in ('out_invoice', 'out_refund')).ids)])._accrue_commissions()
        return posted

    def _commission_reverse_accruals(self):
        for move in self.sudo().filtered(lambda m: m.state == 'posted' and not m.commission_is_reversal and not m.commission_reversed_by_id):
            internal = move.with_context(commission_booking_token=_BOOKING_TOKEN)
            reversal = internal._reverse_moves([{
                'date': fields.Date.context_today(move), 'ref': _('Reversal of commission accrual: %s') % move.name,
                'commission_source_invoice_id': move.commission_source_invoice_id.id, 'commission_is_reversal': True,
                'commission_debit_snapshot_id': move.commission_debit_snapshot_id.id, 'commission_credit_snapshot_id': move.commission_credit_snapshot_id.id,
            }])
            reversal.action_post()
            internal.commission_reversed_by_id = reversal.id

    def _reverse_moves(self, default_values_list=None, cancel=False):
        if self.filtered('commission_source_invoice_id') and self.env.context.get('commission_booking_token') is not _BOOKING_TOKEN:
            raise UserError(_('Reverse commission accruals through their source invoice.'))
        return super()._reverse_moves(default_values_list, cancel)

    def _commission_before_reset(self):
        if self.filtered('commission_source_invoice_id'):
            raise UserError(_('Generated commission entries cannot be reset or cancelled manually.'))
        return self.env['sales.commission.entry'].sudo().search([('move_id', 'in', self.ids)]).accrual_move_id

    def button_draft(self):
        accruals = self._commission_before_reset()
        result = super().button_draft()
        accruals._commission_reverse_accruals()
        return result

    def button_cancel(self):
        accruals = self._commission_before_reset()
        result = super().button_cancel()
        accruals._commission_reverse_accruals()
        return result

    def unlink(self):
        if self.filtered('commission_source_invoice_id'):
            raise UserError(_('Commission journal entries must remain in the audit trail.'))
        return super().unlink()


class MoveLine(models.Model):
    _inherit = 'account.move.line'

    @api.model_create_multi
    def create(self, vals_list):
        if self.env.context.get('commission_booking_token') is not _BOOKING_TOKEN:
            default_move = self.env.context.get('default_move_id')
            move_ids = [v.get('move_id', default_move) for v in vals_list if v.get('move_id', default_move)]
            if self.env['account.move'].sudo().browse(move_ids).filtered('commission_source_invoice_id'):
                raise UserError(_('Generated commission lines are read-only.'))
        lines = super().create(vals_list)
        if self.env.context.get('commission_booking_token') is not _BOOKING_TOKEN and lines.move_id.sudo().filtered('commission_source_invoice_id'):
            raise UserError(_('Generated commission lines are read-only.'))
        return lines

    def write(self, vals):
        protected = {'balance', 'debit', 'credit', 'account_id', 'amount_currency', 'currency_id', 'move_id', 'partner_id', 'tax_ids', 'quantity', 'price_unit', 'discount', 'name'}
        moves = self.move_id | self.env['account.move'].browse(vals.get('move_id'))
        if self.env.context.get('commission_booking_token') is not _BOOKING_TOKEN and protected & vals.keys() and moves.sudo().filtered('commission_source_invoice_id'):
            raise UserError(_('Generated commission lines are read-only.'))
        return super().write(vals)

    def unlink(self):
        if self.env.context.get('commission_booking_token') is not _BOOKING_TOKEN and self.move_id.sudo().filtered('commission_source_invoice_id'):
            raise UserError(_('Generated commission lines must remain in the audit trail.'))
        return super().unlink()
