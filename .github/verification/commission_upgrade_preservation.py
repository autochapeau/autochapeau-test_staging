"""Seed legacy TEST records before source replacement; compare after upgrade.

Run inside the TEST Odoo shell. The before phase must run against the old
checkout and registry. Baselines stay in Odoo's persistent data directory.
"""
import json
import os
from pathlib import Path

from psycopg2 import sql
from odoo import Command, fields, tools
from odoo.modules.module import get_manifest


assert env.cr.dbname in ('autochapeau_prod_test', 'commission_preservation_legacy_20261109'), 'This audit is restricted to TEST and its named local rehearsal.'
phase = os.environ['COMMISSION_UPGRADE_PHASE']
audit_id = os.environ['COMMISSION_UPGRADE_AUDIT_ID']
assert len(audit_id) == 40 and all(c in '0123456789abcdef' for c in audit_id)
directory = Path(tools.config['data_dir']) / 'commission_upgrade_preservation'
directory.mkdir(parents=True, exist_ok=True)
baseline_path = directory / (audit_id + '.before.json')
result_path = directory / (audit_id + '.result.json')
skip_path = directory / (audit_id + '.not-required.json')


def seed_legacy_data():
    company = env.company
    users = env['res.users'].search([
        ('share', '=', False), ('active', '=', True),
        ('company_ids', 'in', company.ids)], order='id', limit=2)
    assert len(users) == 2, 'Two existing internal TEST users are needed.'
    alice, bob = users
    label = 'QA UPGRADE ' + audit_id[:8]
    ctx = dict(env.context, tracking_disable=True, mail_create_nosubscribe=True,
               mail_notrack=True, no_reset_password=True)
    qa = env(context=ctx)
    revenue = qa['account.account'].create({'name': label + ' revenue',
        'code': 'Q' + audit_id[:8] + 'R', 'account_type': 'income', 'company_id': company.id})
    receivable = qa['account.account'].create({'name': label + ' receivable',
        'code': 'Q' + audit_id[:8] + 'C', 'account_type': 'asset_receivable',
        'reconcile': True, 'company_id': company.id})
    journal = qa['account.journal'].create({'name': label + ' sales', 'code': 'Q' + audit_id[:4],
        'type': 'sale', 'company_id': company.id, 'default_account_id': revenue.id,
        'edi_format_ids': [Command.clear()]})
    partner = qa['res.partner'].create({'name': label + ' fictional customer',
        'email': False, 'property_account_receivable_id': receivable.id})
    brand = qa['fleet.vehicle.model.brand'].create({'name': label})
    model = qa['fleet.vehicle.model'].create({'name': label, 'brand_id': brand.id})
    vehicle = qa['fleet.vehicle'].create({'model_id': model.id, 'license_plate': 'QA-' + audit_id[:8],
        'vin_sn': 'QA' + audit_id[:15], 'driver_id': partner.id})
    team = qa['crm.team'].create({'name': label, 'company_id': company.id,
        'commission_level': 'branch', 'member_ids': [Command.set(users.ids)], 'user_id': False})
    category = qa['product.category'].create({'name': label + ' product category'})
    service_category = qa['commission.category'].create({'name': label + ' service category'})
    product = qa['product.product'].create({'name': label + ' goods', 'detailed_type': 'consu',
        'categ_id': category.id, 'property_account_income_id': revenue.id, 'taxes_id': [Command.clear()]})
    service = qa['product.product'].create({'name': label + ' service', 'detailed_type': 'service',
        'commission_category_id': service_category.id,
        'property_account_income_id': revenue.id, 'taxes_id': [Command.clear()]})
    today = fields.Date.context_today(qa['sales.commission.rule'])
    month = today.replace(day=1)
    target = qa['sales.commission.target'].create({'team_id': team.id, 'company_id': company.id,
        'month': month, 'amount': 3000, 'period_type': 'month', 'member_target_ids': [
            Command.create({'user_id': alice.id, 'amount': 1000}),
            Command.create({'user_id': bob.id, 'amount': 2000})]})
    common = {'company_id': company.id, 'date_from': month, 'apply_discount_adjustment': False}
    product_rule = qa['sales.commission.rule'].create(dict(common, name=label + ' legacy product tiers',
        user_id=alice.id, kind='product', category_id=category.id, rate=10,
        tier_ids=[Command.create({'achievement_from': 0, 'achievement_to': 99.99, 'rate': 2}),
                  Command.create({'achievement_from': 100, 'rate': 4})]))
    service_rule = qa['sales.commission.rule'].create(dict(common, name=label + ' legacy service tiers',
        user_id=alice.id, kind='service', service_category_id=service_category.id, rate=7,
        tier_ids=[Command.create({'achievement_from': 0, 'achievement_to': 99.99, 'rate': 3}),
                  Command.create({'achievement_from': 100, 'rate': 5})]))
    fixed_rule = qa['sales.commission.rule'].create(dict(common, name=label + ' legacy fixed rate',
        user_id=bob.id, kind='product', category_id=category.id, rate=6))
    archived_rule = product_rule.copy({'name': label + ' archived rule', 'active': False,
                                      'tier_ids': [Command.clear()], 'rate': 9})

    def invoice(user, item, price):
        order = qa['sale.order'].create({'partner_id': partner.id, 'user_id': user.id,
            'team_id': team.id, 'order_type': 'intern', 'vehicle_id': vehicle.id})
        sale_line = qa['sale.order.line'].create({'order_id': order.id, 'product_id': item.id,
            'product_uom_qty': 1, 'price_unit': price, 'tax_id': [Command.clear()]})
        move = qa['account.move'].create({'move_type': 'out_invoice', 'partner_id': partner.id,
            'invoice_date': today, 'journal_id': journal.id, 'invoice_line_ids': [Command.create({
                'product_id': item.id, 'quantity': 1, 'price_unit': price,
                'account_id': revenue.id, 'tax_ids': [Command.clear()],
                'sale_line_ids': [Command.set(sale_line.ids)]})]})
        move.action_post()
        return move

    goods_invoice = invoice(alice, product, 900)
    service_invoice = invoice(alice, service, 100)
    fixed_invoice = invoice(bob, product, 200)
    refund = goods_invoice._reverse_moves([{'invoice_date': today}])
    refund.invoice_line_ids.filtered(lambda line: line.product_id == product).quantity = .25
    refund.action_post()
    invoices = goods_invoice | service_invoice | fixed_invoice | refund
    entries = qa['sales.commission.entry'].search([('move_id', 'in', invoices.ids)])
    assert len(entries) == 4 and all(entry.status == 'earned' for entry in entries), 'QA invoices must calculate on old code.'
    for move, rate, amount in ((goods_invoice, 2, 18), (service_invoice, 5, 5),
                               (fixed_invoice, 6, 12), (refund, 2, -4.5)):
        entry = entries.filtered(lambda value: value.move_id == move)
        assert len(entry) == 1 and entry.rate == rate and company.currency_id.is_zero(entry.amount - amount)
    return {'label': label, 'rule_ids': (product_rule | service_rule | fixed_rule | archived_rule).ids,
        'tier_ids': (product_rule | service_rule).tier_ids.ids, 'team_id': team.id,
        'target_id': target.id, 'member_target_ids': target.member_target_ids.ids,
        'invoice_ids': invoices.ids, 'entry_ids': entries.ids,
        'expected_commissions': [18, 5, 12, -4.5]}


def fingerprint(table, selected=None, excluded=()):
    env.cr.execute('SELECT column_name FROM information_schema.columns WHERE table_schema=current_schema() '
                   'AND table_name=%s ORDER BY ordinal_position', [table])
    available = [row[0] for row in env.cr.fetchall()]
    assert available and 'id' in available, table
    columns = selected or [name for name in available if name not in excluded]
    assert set(columns) <= set(available), (table, set(columns) - set(available))
    query = sql.SQL("SELECT count(*), md5(COALESCE(string_agg(md5(row_to_json(t)::text), '' ORDER BY id), '')) "
                    "FROM (SELECT {columns} FROM {table}) t").format(
                        columns=sql.SQL(', ').join(map(sql.Identifier, columns)), table=sql.Identifier(table))
    env.cr.execute(query)
    count, digest = env.cr.fetchone()
    return {'columns': columns, 'count': count, 'digest': digest}


def normalized_rules():
    rules = env['sales.commission.rule'].with_context(active_test=False).search([], order='id')
    return [{'id': rule.id, 'scope': getattr(rule, 'scope', 'people'),
        'team_id': rule.team_id.id if 'team_id' in rule._fields else False,
        'user_ids': sorted((rule._scope_users() if hasattr(rule, '_scope_users') else rule.user_id).ids)
                    if getattr(rule, 'scope', 'people') == 'people' else []} for rule in rules]


def normalized_tiers():
    tiers = env['sales.commission.tier'].search([], order='id')
    values = []
    for tier in tiers:
        kind = tier.kind if 'kind' in tier._fields and tier.kind else tier.rule_id.kind
        category = (tier.category_id if kind == 'product' else tier.service_category_id) \
            if 'kind' in tier._fields and tier.kind else (
                tier.rule_id.category_id if kind == 'product' else tier.rule_id.service_category_id)
        values.append({'id': tier.id, 'rule_id': tier.rule_id.id, 'kind': kind, 'category_id': category.id})
    return values


if phase == 'before':
    if baseline_path.exists():
        baseline = json.loads(baseline_path.read_text())
        print('COMMISSION_PRESERVATION_BEFORE=' + json.dumps({'reused': True, 'fixture': baseline['fixture']}))
    elif 'user_ids' in env['sales.commission.rule']._fields:
        # This one-time legacy migration audit must not seed invoices on every
        # unrelated future deployment after the new schema is already installed.
        skip_path.write_text(json.dumps({'reason': 'Multi-salesperson rules already installed.'}), encoding='utf-8')
        print('COMMISSION_PRESERVATION_BEFORE=not_required_already_migrated')
        env.cr.rollback()
    else:
        old_version = env['ir.module.module'].search([('name', '=', 'sales_region_commission')]).latest_version
        fixture = seed_legacy_data()
        env.flush_all()
        tables = {}
        omitted = ('write_uid', 'write_date')
        for table in ('sales_commission_rule', 'sales_commission_tier', 'sales_commission_target',
                      'sales_commission_target_member', 'sales_commission_entry', 'commission',
                      'commission_section', 'commission_discount_section', 'commission_target_job',
                      'commission_target_employee', 'commission_settlement', 'commission_settlement_line',
                      'technicians_commission_settlement', 'technicians_commission_settlement_line'):
            excluded = omitted
            if table == 'sales_commission_rule':
                excluded += ('user_id', 'scope', 'team_id')
            if table == 'sales_commission_tier':
                excluded += ('kind', 'category_id', 'service_category_id')
            tables[table] = fingerprint(table, excluded=excluded)
        selected_tables = {
            'account_move': 'id name state move_type company_id currency_id invoice_date date amount_untaxed amount_tax amount_total amount_residual',
            'account_move_line': 'id move_id account_id partner_id product_id quantity price_unit discount balance debit credit amount_currency price_subtotal price_total display_type company_id currency_id',
            'sale_order': 'id name state company_id user_id team_id partner_id amount_untaxed amount_tax amount_total currency_id',
            'product_category': 'id name parent_id', 'commission_category': 'id name',
        }
        for table, names in selected_tables.items():
            tables[table] = fingerprint(table, selected=names.split())
        baseline = {'database': env.cr.dbname, 'audit_id': audit_id, 'old_version': old_version,
                    'old_source_version': get_manifest('sales_region_commission')['version'],
                    'legacy_single_user_orm': 'user_ids' not in env['sales.commission.rule']._fields,
                    'fixture': fixture, 'tables': tables, 'rules': normalized_rules(), 'tiers': normalized_tiers()}
        # Commit fixtures first; publish a baseline only after successful persistence.
        env.cr.commit()
        temporary = baseline_path.with_suffix('.tmp')
        temporary.write_text(json.dumps(baseline, indent=2), encoding='utf-8')
        temporary.replace(baseline_path)
        print('COMMISSION_PRESERVATION_BEFORE=' + json.dumps({'version': old_version,
            'old_source_version': baseline['old_source_version'],
            'legacy_single_user_orm': baseline['legacy_single_user_orm'],
            'fixture': fixture, 'table_counts': {name: value['count'] for name, value in tables.items()}}))
elif phase == 'after':
    if skip_path.exists():
        print('COMMISSION_PRESERVATION_AFTER=not_required_already_migrated')
        env.cr.rollback()
        raise SystemExit(0)
    baseline = json.loads(baseline_path.read_text())
    differences = []
    results = {}
    for table, before in baseline['tables'].items():
        after = fingerprint(table, selected=before['columns'])
        preserved = before == after
        results[table] = {'before_count': before['count'], 'after_count': after['count'],
                          'values_unchanged': preserved}
        if not preserved:
            differences.append(table)
    for label, current in (('rule_assignments', normalized_rules()), ('tier_categories', normalized_tiers())):
        expected = baseline['rules' if label == 'rule_assignments' else 'tiers']
        results[label] = {'preserved': current == expected, 'count': len(expected)}
        if current != expected:
            differences.append(label)
    result = {'database': env.cr.dbname, 'audit_id': audit_id, 'old_version': baseline['old_version'],
        'old_source_version': baseline.get('old_source_version'),
        'legacy_single_user_orm': baseline.get('legacy_single_user_orm'),
        'new_version': env['ir.module.module'].search([('name', '=', 'sales_region_commission')]).latest_version,
        'fixture': baseline['fixture'], 'checks': results, 'differences': differences,
        'passed': not differences, 'baseline_path': str(baseline_path)}
    result_path.write_text(json.dumps(result, indent=2), encoding='utf-8')
    print('COMMISSION_PRESERVATION_AFTER=' + json.dumps(result, sort_keys=True))
    assert not differences, 'Unexpected data changes after upgrade: ' + ', '.join(differences)
    env.cr.rollback()
else:
    raise ValueError('Unsupported preservation phase')
