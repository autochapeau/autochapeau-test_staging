"""Offline backup and preservation check; run in the application's runtime."""
import datetime
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import copy
from lxml import etree

import odoo
from odoo.tools import config
from odoo.tools import exec_pg_environ, find_pg_tool

config.parse_config([])
database, mode = sys.argv[1:3]
data_dir = Path(config['data_dir'])
checkpoint = data_dir / 'production-release-checkpoint.json'
TABLES = {
    'account_move': ['id','name','state','move_type','partner_id','company_id','journal_id','amount_total','amount_residual'],
    'account_move_line': ['id','move_id','account_id','partner_id','debit','credit','balance','amount_currency','currency_id','analytic_distribution'],
    'account_payment': ['id','move_id','amount','partner_id','payment_type'],
    'res_partner': ['id','name','active','ref','mobile','mobile_normalized','phone'],
    'sale_order': ['id','name','state','partner_id','user_id','team_id','amount_total'],
    'car_work_order': ['id','state','partner_id','vehicle_id','branch_id','company_id'],
    'car_workorder_service': ['id','workorder_id','product_id','state'],
    'car_workorder_product': None,
    'car_bom': None,
    'car_service_part': None,
    'stock_quant': ['id','product_id','location_id','quantity','reserved_quantity'],
    'stock_move': ['id','state','product_id','product_uom_qty','quantity','location_id','location_dest_id'],
    'stock_move_line': ['id','move_id','product_id','product_uom_id','quantity','location_id','location_dest_id','lot_id'],
    'account_asset': ['id','state','purchase_value','salvage_value'],
    'commission': None,
    'commission_section': None,
    'commission_discount_section': None,
    'commission_target_job': None,
    'commission_target_employee': None,
    'commission_settlement': None,
    'commission_settlement_line': None,
    'technicians_commission_settlement': None,
    'technicians_commission_settlement_line': None,
    'sales_commission_entry': None,
    'sales_commission_target': None,
    'sales_commission_target_member': None,
    'sales_commission_rule': None,
    'sales_commission_tier': None,
    'commission_category': None,
    'product_category': ['id', 'name', 'parent_id'],
    'maintenance_claim': None,
    'maintenance_claim_part': None,
    'ziwo_history': None,
}


def snapshot(spec=None):
    result = {}
    with odoo.sql_db.db_connect(database).cursor() as cr:
        for table, wanted in (spec or TABLES).items():
            cr.execute("SELECT column_name FROM information_schema.columns WHERE table_schema='public' AND table_name=%s ORDER BY ordinal_position", [table])
            available = [r[0] for r in cr.fetchall()]
            if not available:
                if spec:
                    raise RuntimeError('Existing table disappeared: ' + table)
                continue
            excluded = ('write_date','write_uid','create_date','create_uid')
            if table == 'sales_commission_rule':
                # The legacy owner moves to user_ids; compare its meaning below.
                excluded += ('user_id',)
            columns = wanted['columns'] if spec else [c for c in (wanted or available) if c in available and c not in excluded]
            if not set(columns).issubset(available):
                raise RuntimeError('Existing columns disappeared: ' + table)
            # Identifiers come only from the fixed allowlist / our private snapshot.
            digest = hashlib.sha256()
            cr.execute('SELECT ' + ','.join('"' + c + '"' for c in columns) + ' FROM "' + table + '" ORDER BY id')
            count = 0
            while True:
                rows = cr.fetchmany(1000)
                if not rows:
                    break
                for row in rows:
                    digest.update(json.dumps(row, default=str, sort_keys=True, separators=(',',':')).encode())
                    digest.update(b'\n')
                    count += 1
            result[table] = {'columns': columns, 'count': count, 'sha256': digest.hexdigest()}
    return result


def commission_assignments():
    """Read old/new rule recipients and tier categories without a registry.

    The backup runs before the new model columns exist. Keep every rule/tier ID,
    including archived rules, and compare the effective old and new values.
    """
    with odoo.sql_db.db_connect(database).cursor() as cr:
        def columns(table):
            cr.execute("SELECT column_name FROM information_schema.columns WHERE table_schema='public' AND table_name=%s", [table])
            return {row[0] for row in cr.fetchall()}

        rule_columns = columns('sales_commission_rule')
        if not rule_columns:
            return {'rules': [], 'tiers': []}
        scope = 'scope' if 'scope' in rule_columns else "'people'"
        team = 'team_id' if 'team_id' in rule_columns else 'NULL'
        cr.execute('SELECT id,user_id,' + scope + ',' + team + ' FROM sales_commission_rule ORDER BY id')
        rules = cr.fetchall()
        cr.execute("SELECT to_regclass('public.sales_commission_rule_user_rel')")
        members = {}
        if cr.fetchone()[0]:
            cr.execute('SELECT rule_id,user_id FROM sales_commission_rule_user_rel ORDER BY rule_id,user_id')
            for rule_id, user_id in cr.fetchall():
                members.setdefault(rule_id, []).append(user_id)
        recipients = [{'id': rule_id, 'scope': rule_scope or 'people', 'team_id': team_id,
            'user_ids': members.get(rule_id) or ([owner] if owner else [])}
            for rule_id, owner, rule_scope, team_id in rules]
        tier_columns = columns('sales_commission_tier')
        if 'calculation_method' in rule_columns:
            method = 'r.calculation_method'
        elif tier_columns:
            method = "CASE WHEN EXISTS (SELECT 1 FROM sales_commission_tier t WHERE t.rule_id=r.id) THEN 'tiers' ELSE 'fixed' END"
        else:
            method = "'fixed'"
        cr.execute('SELECT r.id,' + method + ' FROM sales_commission_rule r ORDER BY r.id')
        methods = dict(cr.fetchall())
        for recipient in recipients:
            recipient['calculation_method'] = methods[recipient['id']]
        if not tier_columns:
            return {'rules': recipients, 'tiers': []}
        kind = 'COALESCE(t.kind,r.kind)' if 'kind' in tier_columns else 'r.kind'
        product = 'CASE WHEN t.kind IS NULL THEN r.category_id ELSE t.category_id END' if 'kind' in tier_columns else 'r.category_id'
        service = 'CASE WHEN t.kind IS NULL THEN r.service_category_id ELSE t.service_category_id END' if 'kind' in tier_columns else 'r.service_category_id'
        cr.execute('SELECT t.id,t.rule_id,' + kind + ',CASE WHEN (' + kind + ")='product' THEN " + product + ' ELSE ' + service +
                   ' END FROM sales_commission_tier t JOIN sales_commission_rule r ON r.id=t.rule_id ORDER BY t.id')
        tiers = [{'id': tier_id, 'rule_id': rule_id, 'kind': category_kind, 'category_id': category_id}
                 for tier_id, rule_id, category_kind, category_id in cr.fetchall()]
        return {'rules': recipients, 'tiers': tiers}


def repair_qr_dependency(folder):
    """Move a manual localization field without loading an out-of-date registry.

    A cold upgrade validates accounting views before l10n_sa loads. Preserve
    the field in a localization-owned inherited view, including translations.
    The full DB backup and original architecture remain available to restore.
    """
    with odoo.sql_db.db_connect(database).cursor() as cr:
        cr.execute("SELECT v.id,v.arch_db FROM ir_ui_view v JOIN ir_model_data d ON d.model='ir.ui.view' AND d.res_id=v.id WHERE d.module='account' AND d.name='view_move_form'")
        root_id, translations = cr.fetchone()
        originals = copy.deepcopy(translations)
        inherited = {}
        for lang, arch in translations.items():
            tree = etree.fromstring(arch.encode())
            nodes = tree.xpath("//field[@name='l10n_sa_qr_code_str']")
            if not nodes:
                continue
            patches = etree.Element('data')
            for node in nodes:
                parent = node.getparent()
                # Anchor by the original parent position and a nearby field.
                previous = node.getprevious()
                following = node.getnext()
                while previous is not None and previous in nodes:
                    previous = previous.getprevious()
                while following is not None and following in nodes:
                    following = following.getnext()
                anchor = previous if previous is not None else following
                position = 'after' if previous is not None else 'before' if following is not None else 'inside'
                expr = tree.getroottree().getpath(anchor if anchor is not None else parent)
                patch = etree.SubElement(patches, 'xpath', expr=expr, position=position)
                patch.append(copy.deepcopy(node))
            for node in nodes:
                node.getparent().remove(node)
            inherited[lang] = etree.tostring(patches, encoding='unicode')
            translations[lang] = etree.tostring(tree, encoding='unicode')
        if not inherited:
            print('PRODUCTION_QR_DEPENDENCY_REPAIR=not_needed', flush=True)
            return
        assert 'en_US' in inherited, 'Review root view translations before upgrade'
        cr.execute("SELECT state FROM ir_module_module WHERE name='l10n_sa'")
        assert cr.fetchone() == ('installed',), 'Saudi localization must already be installed'
        cr.execute("SELECT 1 FROM ir_model_data WHERE module='l10n_sa' AND name='production_preserved_qr_move_form'")
        assert not cr.fetchone(), 'Existing QR repair requires review'
        (folder/'account_move_root_view_before.json').write_text(json.dumps(originals, ensure_ascii=False), encoding='utf-8')
        cr.execute("INSERT INTO ir_ui_view (name,model,type,mode,inherit_id,priority,active,arch_db) VALUES (%s,'account.move','form','extension',%s,15,true,%s::jsonb) RETURNING id", ['Preserved Saudi QR field',root_id,json.dumps(inherited)])
        new_id = cr.fetchone()[0]
        cr.execute("INSERT INTO ir_model_data (module,name,model,res_id,noupdate) VALUES ('l10n_sa','production_preserved_qr_move_form','ir.ui.view',%s,true)", [new_id])
        cr.execute('UPDATE ir_ui_view SET arch_db=%s::jsonb WHERE id=%s', [json.dumps(translations),root_id])
        cr.commit()
        print('PRODUCTION_QR_DEPENDENCY_REPAIR=preserved', flush=True)


if mode == 'backup':
    os.umask(0o077)
    mounts = [line.split()[4].replace('\\040', ' ') for line in Path('/proc/self/mountinfo').read_text().splitlines()]
    assert any(m != '/' and (str(data_dir) == m or str(data_dir).startswith(m + '/')) for m in mounts), 'Backup directory must be on a persistent application mount'
    folder = data_dir / 'production-release-backups' / datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    folder.mkdir(parents=True, exist_ok=False)
    filestore = Path(config.filestore(database)).resolve()
    size = sum(p.stat().st_size for p in filestore.rglob('*') if p.is_file()) if filestore.exists() else 0
    with odoo.sql_db.db_connect(database).cursor() as cr:
        cr.execute('SELECT pg_database_size(current_database())')
        database_size = cr.fetchone()[0]
    if shutil.disk_usage(data_dir).free < size + database_size + 512 * 1024**2:
        raise RuntimeError('Insufficient backup disk space; upgrade has not started.')
    before = snapshot()
    (folder / 'before.json').write_text(json.dumps(before, indent=2))
    (folder / 'commission_assignments.before.json').write_text(json.dumps(commission_assignments(), indent=2))
    dump = folder / 'database.dump'
    subprocess.run([find_pg_tool('pg_dump'), '--no-owner', '--format=c', '--file='+str(dump), database], env=exec_pg_environ(), check=True)
    subprocess.run([find_pg_tool('pg_restore'), '--list', str(dump)], stdout=subprocess.DEVNULL, check=True)
    if filestore.exists():
        with tarfile.open(folder/'filestore.tar.gz', 'w:gz') as archive:
            archive.add(filestore, arcname='filestore')
        with tarfile.open(folder/'filestore.tar.gz', 'r:gz') as archive:
            assert archive.getmembers(), 'Empty filestore archive'
    metadata = {'database': database, 'backup_directory': str(folder), 'database_bytes': dump.stat().st_size,
                'filestore_present': filestore.exists(), 'filestore_source_bytes': size,
                'tables': {t:v['count'] for t,v in before.items()}}
    (folder/'backup.json').write_text(json.dumps(metadata, indent=2))
    checkpoint.write_text(json.dumps({'directory':str(folder), 'database':database}))
    print('PRODUCTION_BACKUP=' + json.dumps(metadata), flush=True)
    repair_qr_dependency(folder)
elif mode == 'verify':
    state = json.loads(checkpoint.read_text())
    assert state['database'] == database
    folder = Path(state['directory'])
    before = json.loads((folder/'before.json').read_text())
    after = snapshot(before)
    (folder/'after.json').write_text(json.dumps(after, indent=2))
    changed = [t for t in before if before[t] != after[t]]
    assert not changed, 'Business data changed during upgrade: ' + ','.join(changed)
    assignments_before = json.loads((folder / 'commission_assignments.before.json').read_text())
    assignments_after = commission_assignments()
    (folder / 'commission_assignments.after.json').write_text(json.dumps(assignments_after, indent=2))
    assert assignments_before == assignments_after, 'Commission salesperson assignments or tier categories changed during upgrade.'
    print('PRODUCTION_COMMISSION_ASSIGNMENTS_PRESERVED=' + json.dumps({
        'rules': len(assignments_after['rules']), 'tiers': len(assignments_after['tiers'])}), flush=True)
    print('PRODUCTION_DATA_PRESERVED=' + json.dumps({t:v['count'] for t,v in after.items()}), flush=True)
    # Supplied by the maintenance launcher; smoke checks roll their transaction back.
    subprocess.run(['odoo','shell','-d',database,'--no-http','--max-cron-threads=0'], input=SMOKE_SOURCE, text=True, check=True)
else:
    raise ValueError('Unknown release mode')
