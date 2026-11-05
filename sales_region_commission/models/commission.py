import calendar
from dateutil.relativedelta import relativedelta
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError, AccessError


class Team(models.Model):
    _inherit = 'crm.team'

    commission_parent_id = fields.Many2one('crm.team', string='Parent region', check_company=True, ondelete='restrict')
    commission_level = fields.Selection([('region', 'Region'), ('area', 'Subregion'), ('branch', 'Branch')], default='branch', required=True)
    commission_manager_id = fields.Many2one('res.users', string='Commission manager', check_company=True)

    def write(self, vals):
        if {'commission_parent_id', 'commission_level', 'commission_manager_id'} & vals.keys():
            if not self.env.su and not self.env.user.has_group('sales_region_commission.group_admin'):
                raise AccessError(_('Only commission administrators can change region assignments.'))
        result = super().write(vals)
        if {'commission_parent_id', 'commission_manager_id', 'user_id', 'company_id', 'active'} & vals.keys():
            self.env.registry.clear_cache()
        return result

    @api.model_create_multi
    def create(self, vals_list):
        if any({'commission_parent_id', 'commission_manager_id', 'commission_level'} & v.keys() for v in vals_list):
            if not self.env.su and not self.env.user.has_group('sales_region_commission.group_admin'):
                raise AccessError(_('Only commission administrators can configure regions.'))
        teams = super().create(vals_list)
        self.env.registry.clear_cache()
        return teams

    @api.constrains('commission_parent_id', 'commission_level', 'company_id')
    def _check_commission_hierarchy(self):
        levels = {'region': 0, 'area': 1, 'branch': 2}
        for team in self:
            seen = team
            parent = team.commission_parent_id
            while parent:
                if parent in seen:
                    raise ValidationError(_('The region hierarchy cannot contain a cycle.'))
                seen |= parent
                parent = parent.commission_parent_id
            parent = team.commission_parent_id
            if parent and (parent.company_id != team.company_id or levels[parent.commission_level] >= levels[team.commission_level]):
                raise ValidationError(_('Choose a parent at a higher level in the same company.'))
            children = self.search([('commission_parent_id', '=', team.id)])
            if any(levels[c.commission_level] <= levels[team.commission_level] or c.company_id != team.company_id for c in children):
                raise ValidationError(_('The selected level/company conflicts with existing child teams.'))

    def _commission_descendants(self):
        result = self
        pending = self
        while pending:
            pending = self.with_context(active_test=False).search([('commission_parent_id', 'in', pending.ids)]) - result
            result |= pending
        return result


class Users(models.Model):
    _inherit = 'res.users'

    commission_managed_team_ids = fields.One2many('crm.team', 'commission_manager_id')
    commission_leader_team_ids = fields.One2many('crm.team', 'user_id', groups='base.group_system', readonly=True)

    def _commission_scope_roots(self):
        self.ensure_one()
        companies = self.company_ids & self.env.companies
        # Only team metadata is elevated. Ledger/target queries retain their
        # normal ACLs and company record rules. No leadership is copied or changed.
        return self.env['crm.team'].sudo().with_context(active_test=False).search([
            ('company_id', 'in', [False] + companies.ids),
            '|', ('user_id', '=', self.id), ('commission_manager_id', '=', self.id),
        ])

    def commission_visible_team_ids(self):
        self.ensure_one()
        if not self.has_group('sales_region_commission.group_manager'):
            return []
        companies = self.company_ids & self.env.companies
        return self._commission_scope_roots()._commission_descendants().filtered(
            lambda t: not t.company_id or t.company_id in companies).ids


class Rule(models.Model):
    _name = 'sales.commission.rule'
    _description = 'Sales commission rate'
    _order = 'date_from desc, id desc'
    _check_company_auto = True

    name = fields.Char(required=True)
    active = fields.Boolean(default=True)
    company_id = fields.Many2one('res.company', required=True, default=lambda self: self.env.company)
    user_id = fields.Many2one('res.users', string='Salesperson', required=True, check_company=True)
    kind = fields.Selection([('product', 'Product category'), ('service', 'Service category')], required=True, default='product')
    category_id = fields.Many2one('product.category', string='Product category')
    service_category_id = fields.Many2one('commission.category', string='Service category')
    rate = fields.Float(string='Commission %', required=True, digits=(16, 4))
    date_from = fields.Date(required=True, default=fields.Date.context_today)
    date_to = fields.Date()

    @api.constrains('active', 'user_id', 'company_id', 'kind', 'category_id', 'service_category_id', 'rate', 'date_from', 'date_to')
    def _check_rule(self):
        for rule in self:
            if not 0 <= rule.rate <= 100 or (rule.date_to and rule.date_to < rule.date_from):
                raise ValidationError(_('Use a rate between 0 and 100 and a valid date range.'))
            if (rule.kind == 'product' and (not rule.category_id or rule.service_category_id)) or (rule.kind == 'service' and (not rule.service_category_id or rule.category_id)):
                raise ValidationError(_('Select only the category matching the rule type.'))
            if not rule.active:
                continue
            domain = [('id', '!=', rule.id), ('active', '=', True), ('user_id', '=', rule.user_id.id),
                      ('company_id', '=', rule.company_id.id), ('kind', '=', rule.kind),
                      ('category_id', '=', rule.category_id.id), ('service_category_id', '=', rule.service_category_id.id),
                      '|', ('date_to', '=', False), ('date_to', '>=', rule.date_from)]
            if rule.date_to:
                domain += [('date_from', '<=', rule.date_to)]
            if self.search_count(domain):
                raise ValidationError(_('Commission rules for the same salesperson and category must not overlap.'))


class Target(models.Model):
    _name = 'sales.commission.target'
    _description = 'Monthly sales target'
    _rec_name = 'team_id'
    _check_company_auto = True

    team_id = fields.Many2one('crm.team', required=True, check_company=True, ondelete='restrict')
    company_id = fields.Many2one('res.company', required=True, default=lambda self: self.env.company)
    month = fields.Date(required=True, default=lambda self: fields.Date.context_today(self).replace(day=1))
    currency_id = fields.Many2one(related='company_id.currency_id')
    amount = fields.Monetary(required=True)
    _sql_constraints = [('team_month_unique', 'unique(team_id, company_id, month)', 'One target per team and month.')]

    @api.constrains('month', 'amount')
    def _check_target(self):
        for target in self:
            if target.month.day != 1 or target.amount <= 0:
                raise ValidationError(_('Use the first day of the month and a positive target.'))


class Entry(models.Model):
    _name = 'sales.commission.entry'
    _description = 'Posted invoice commission snapshot'
    _order = 'date desc, id desc'
    _check_company_auto = True

    invoice_line_id = fields.Many2one('account.move.line', required=True, ondelete='cascade', index=True)
    move_id = fields.Many2one(related='invoice_line_id.move_id', store=True)
    date = fields.Date(required=True, index=True)
    company_id = fields.Many2one('res.company', required=True, index=True)
    currency_id = fields.Many2one(related='company_id.currency_id')
    user_id = fields.Many2one('res.users', string='Salesperson', index=True)
    team_id = fields.Many2one('crm.team', index=True)
    product_id = fields.Many2one('product.product')
    category_name = fields.Char()
    rule_id = fields.Many2one('sales.commission.rule', ondelete='restrict')
    origin_id = fields.Many2one('sales.commission.entry', ondelete='restrict')
    base = fields.Monetary(string='Net invoiced')
    rate = fields.Float(string='Rate %', digits=(16, 4))
    amount = fields.Monetary(string='Commission')
    status = fields.Selection([('earned', 'Calculated'), ('review', 'Needs review')], required=True)
    note = fields.Char()
    _sql_constraints = [('invoice_line_unique', 'unique(invoice_line_id)', 'This invoice line already has a commission snapshot.')]

    @api.model_create_multi
    def create(self, vals_list):
        if not self.env.su:
            raise AccessError(_('Commission entries are generated by invoice posting.'))
        return super().create(vals_list)

    def write(self, vals):
        if not self.env.su:
            raise AccessError(_('Posted commission snapshots are read-only.'))
        return super().write(vals)

    def unlink(self):
        if not self.env.su:
            raise AccessError(_('Commission entries are managed by invoice state changes.'))
        return super().unlink()

    @api.model
    def dashboard(self, month=False, team_id=False, period_type='month'):
        self.check_access_rights('read')
        start = fields.Date.to_date(month) if month else fields.Date.context_today(self)
        lengths = {'month': 1, 'quarter': 3, 'half': 6, 'year': 12}
        if period_type not in lengths:
            raise ValidationError(_('Select a valid calendar period.'))
        length = lengths[period_type]
        start = start.replace(day=1, month=((start.month - 1) // length) * length + 1)
        end = start + relativedelta(months=length, days=-1)
        domain = [('company_id', '=', self.env.company.id), ('date', '>=', start), ('date', '<=', end)]
        # Build team choices only from the current user's readable ledger/targets.
        targets = self.env['sales.commission.target'].search([('company_id', '=', self.env.company.id), ('month', '<=', end), ('date_end', '>=', start)])
        groups = self.read_group(domain, ['team_id'], ['team_id'], lazy=False)
        teams = self.env['crm.team'].browse([g['team_id'][0] for g in groups if g['team_id']]) | targets.team_id
        if self.env.user.has_group('sales_region_commission.group_manager'):
            teams |= self.env.user._commission_scope_roots().filtered(lambda t: not t.company_id or t.company_id == self.env.company)
        if team_id:
            selected = self.env['crm.team'].browse(int(team_id)) & teams
            if not selected:
                raise AccessError(_('This team is outside your commission scope.'))
            domain += [('team_id', 'in', selected._commission_descendants().ids)]
            targets = targets.filtered(lambda t: t.team_id in selected._commission_descendants())
        target_total = 0
        cursor = start
        personal = not self.env.user.has_group('sales_region_commission.group_manager')
        while cursor <= end:
            current = targets.filtered(lambda target: target.month <= cursor <= target.date_end)
            if personal:
                for target in current:
                    own_share = target.member_target_ids.filtered(lambda share: share.user_id == self.env.user)
                    # Keep legacy undivided targets visible until an administrator distributes them.
                    value = sum(own_share.mapped('amount')) if target.sudo().member_target_ids else target.amount
                    target_total += value / lengths[target.period_type]
            else:
                current_teams = current.team_id
                for target in current.filtered(lambda t: not any(p in current_teams for p in self._team_parents(t.team_id))):
                    target_total += target.amount / lengths[target.period_type]
            cursor += relativedelta(months=1)
        totals = self.read_group(domain, ['base:sum', 'amount:sum'], [], lazy=False)
        total = totals[0] if totals else {}
        people = self.read_group(domain, ['base:sum', 'amount:sum', 'user_id'], ['user_id'], lazy=False)
        people.sort(key=lambda r: r.get('amount', 0), reverse=True)
        daily = self.read_group(domain, ['base:sum', 'amount:sum'], ['date:day'], lazy=False)
        return {'month': str(start), 'period_type': period_type, 'date_end': str(end), 'currency': self.env.company.currency_id.name,
                'net': total.get('base', 0), 'commission': total.get('amount', 0),
                'target': self.env.company.currency_id.round(target_total), 'review': self.search_count(domain + [('status', '=', 'review')]),
                'count': self.search_count(domain), 'refunds': -sum(r['base'] for r in self.read_group(domain + [('base', '<', 0)], ['base:sum'], [], lazy=False)),
                'teams': [{'id': t.id, 'name': t.display_name} for t in teams.sorted('name')],
                'people': [{'id': p['user_id'][0] if p['user_id'] else False, 'name': p['user_id'][1] if p['user_id'] else _('Unassigned'), 'net': p['base'], 'amount': p['amount']} for p in people],
                'daily': [{'label': d['date:day'], 'net': d['base'], 'amount': d['amount']} for d in daily],
                'domain': domain, 'personal': not self.env.user.has_group('sales_region_commission.group_manager')}

    @api.model
    def _team_parents(self, team):
        parents = self.env['crm.team']
        while team.commission_parent_id and team.commission_parent_id not in parents:
            team = team.commission_parent_id
            parents |= team
        return parents


class Invoice(models.Model):
    _inherit = 'account.move'

    commission_entry_ids = fields.One2many('sales.commission.entry', 'move_id')

    def _reverse_moves(self, default_values_list=None, cancel=False):
        return super(Invoice, self.with_context(commission_reversal=True))._reverse_moves(default_values_list, cancel)

    def _post(self, soft=True):
        posted = super()._post(soft=soft)
        posted.filtered(lambda m: m.move_type in ('out_invoice', 'out_refund'))._snapshot_commissions()
        return posted

    def _snapshot_commissions(self):
        Entry = self.env['sales.commission.entry'].sudo()
        for move in self.sudo().filtered(lambda m: m.state == 'posted' and m.move_type in ('out_invoice', 'out_refund')):
            existing = Entry.search([('move_id', '=', move.id)]).invoice_line_id
            for line in move.invoice_line_ids.filtered(lambda l: l.display_type == 'product' and l.product_id
                    and not l.is_downpayment and not getattr(l, 'is_service_advance', False)) - existing:
                sales = line.sale_line_ids.order_id
                users = sales.user_id
                teams = sales.team_id
                user = users if len(users) == 1 else self.env['res.users']
                team = teams if len(teams) == 1 else self.env['crm.team']
                vals = {'invoice_line_id': line.id, 'company_id': move.company_id.id,
                        'date': move.invoice_date or move.date, 'user_id': user.id, 'team_id': team.id,
                        'product_id': line.product_id.id, 'base': -line.balance, 'rate': 0,
                        'amount': 0, 'status': 'review', 'note': _('No matching commission rule or unambiguous sales order.')}
                product = line.product_id
                category = product.commission_category_id if product.detailed_type == 'service' else product.categ_id
                vals['category_name'] = category.display_name
                if move.move_type == 'out_refund':
                    originals = move.reversed_entry_id.invoice_line_ids.filtered(lambda l: l.product_id == product)
                    source = line.commission_source_line_id
                    if source and source in originals:
                        originals = source
                    if line.sale_line_ids:
                        originals = originals.filtered(lambda l: bool(l.sale_line_ids & line.sale_line_ids))
                    origin = Entry.search([('invoice_line_id', 'in', originals.ids)])
                    if len(origin) == 1 and origin.status == 'earned' and origin.invoice_line_id.currency_id == line.currency_id:
                        vals.update(origin_id=origin.id, user_id=origin.user_id.id, team_id=origin.team_id.id,
                                    rule_id=origin.rule_id.id, rate=origin.rate, status='earned', note=False,
                                    category_name=origin.category_name)
                    else:
                        vals['note'] = _('Credit note needs one identifiable calculated original invoice line.')
                elif user and team and all(s.user_id == user and s.team_id == team for s in sales) and len(sales.company_id) == 1 and sales.company_id == move.company_id:
                    rule_domain = [('company_id', '=', move.company_id.id), ('user_id', '=', user.id),
                                   ('date_from', '<=', vals['date']), '|', ('date_to', '=', False), ('date_to', '>=', vals['date'])]
                    rule_domain += [('kind', '=', 'service'), ('service_category_id', '=', category.id)] if product.detailed_type == 'service' else [('kind', '=', 'product'), ('category_id', '=', category.id)]
                    rule = self.env['sales.commission.rule'].sudo().search(rule_domain, limit=2)
                    if len(rule) == 1:
                        rate, achievement, personal_target, note = rule._rate_for_invoice_line(line, team, vals['date'])
                        vals.update(rate=rate or 0, rule_id=rule.id, status='review' if note else 'earned', note=note,
                                    achievement_percent=achievement, personal_target=personal_target)
                vals['amount'] = move.company_id.currency_id.round(vals['base'] * vals['rate'] / 100)
                if vals.get('origin_id'):
                    original_amount = origin.invoice_line_id.amount_currency
                    vals['amount'] = move.company_id.currency_id.round(origin.amount * line.amount_currency / original_amount) if original_amount else 0
                Entry.create(vals)

    def button_draft(self):
        entries = self.env['sales.commission.entry'].sudo().search([('move_id', 'in', self.ids)])
        if self.env['sales.commission.entry'].sudo().search_count([('origin_id', 'in', entries.ids)]):
            raise ValidationError(_('Reset linked credit notes first to preserve their commission audit trail.'))
        result = super().button_draft()
        entries.unlink()
        return result

    def button_cancel(self):
        entries = self.env['sales.commission.entry'].sudo().search([('move_id', 'in', self.ids)])
        if self.env['sales.commission.entry'].sudo().search_count([('origin_id', 'in', entries.ids)]):
            raise ValidationError(_('Reset linked credit notes first.'))
        result = super().button_cancel()
        entries.unlink()
        return result


class InvoiceLine(models.Model):
    _inherit = 'account.move.line'

    commission_source_line_id = fields.Many2one('account.move.line', readonly=True, copy=False, ondelete='set null')

    def _copy_data_extend_business_fields(self, values):
        super()._copy_data_extend_business_fields(values)
        if self.env.context.get('commission_reversal') and self.move_id.move_type == 'out_invoice':
            values['commission_source_line_id'] = self.id


class CalculateWizard(models.TransientModel):
    _name = 'sales.commission.calculate'
    _description = 'Calculate historical posted commissions'

    company_id = fields.Many2one('res.company', required=True, default=lambda self: self.env.company)
    date_from = fields.Date(required=True, default=lambda self: fields.Date.context_today(self).replace(day=1))
    date_to = fields.Date(required=True, default=fields.Date.context_today)
    retry_review = fields.Boolean(string='Retry entries needing review', default=True)

    def action_calculate(self):
        self.ensure_one()
        if not self.env.user.has_group('sales_region_commission.group_admin') or self.company_id not in self.env.companies:
            raise AccessError(_('Commission administrator access in this company is required.'))
        if self.date_to < self.date_from:
            raise ValidationError(_('Choose a valid date range.'))
        moves = self.env['account.move'].sudo().search([
            ('company_id', '=', self.company_id.id), ('state', '=', 'posted'),
            ('move_type', 'in', ['out_invoice', 'out_refund']),
            ('invoice_date', '>=', self.date_from), ('invoice_date', '<=', self.date_to),
        ], order='move_type,invoice_date,id', limit=501)
        if len(moves) > 500:
            raise ValidationError(_('Select a smaller period (maximum 500 invoices per batch).'))
        if self.retry_review:
            self.env['sales.commission.entry'].sudo().search([('move_id', 'in', moves.ids), ('status', '=', 'review')]).unlink()
        moves._snapshot_commissions()
        return {'type': 'ir.actions.act_window', 'name': _('Calculated commission entries'),
                'res_model': 'sales.commission.entry', 'view_mode': 'tree,pivot,form',
                'domain': [('move_id', 'in', moves.ids)]}
