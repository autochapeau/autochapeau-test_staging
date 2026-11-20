"""Archive only fictional website fixtures and restore exact pre-project TEST SMS settings."""
import json,os
from pathlib import Path
import odoo
from odoo.tools import config
config.parse_config([])
database='autochapeau_prod_test'
before=json.loads((Path(config['data_dir'])/'website-rollback-backups/20261121/website-state.json').read_text())
original=json.loads(Path('/tmp/website-original-sms.json').read_text())
assert before['database']==original['database']==database
with odoo.sql_db.db_connect(database).cursor() as cr:
    cr.execute('SELECT current_database()');assert cr.fetchone()[0]==database
    cr.execute("SELECT key,value FROM ir_config_parameter WHERE key IN ('infinito_client_id','infinito_client_password','portal_api.allow_test_otp')")
    assert dict(cr.fetchall())==before['parameters'],'SMS settings changed after snapshot; preserve newer settings'
    # A newer Production-to-TEST refresh must retain its own provider settings.
    restore_sms=before['parameters']==original['feature_configuration']
    if restore_sms:
        for key,value in original['previous_configuration'].items():
            assert key in ('infinito_client_id','infinito_client_password','portal_api.allow_test_otp')
            if value in (False,None):cr.execute('DELETE FROM ir_config_parameter WHERE key=%s',[key])
            else:cr.execute('INSERT INTO ir_config_parameter (key,value) VALUES (%s,%s) ON CONFLICT (key) DO UPDATE SET value=EXCLUDED.value',[key,str(value)])
    cr.execute("UPDATE portal_offer SET active=false WHERE name::text ILIKE '%DEMO Website QA Offer%'");offers=cr.rowcount
    cr.execute("UPDATE portal_statistic SET active=false WHERE name->>'en_US'='Completed services' AND metric='services'");counters=cr.rowcount
    cr.execute("SELECT name->>'en_US' FROM product_template WHERE id=4495")
    qa_present=cr.fetchone()==('DEMO Website QA Media Service',)
    if qa_present:
        cr.execute('UPDATE product_template SET active=false WHERE id=4495')
        cr.execute('UPDATE product_product SET active=false,is_published=false WHERE id=6902 AND product_tmpl_id=4495')
    names=['product_template_form_website_card','product_category_website_image_form','google_review_source_tree','google_review_source_form']
    cr.execute("UPDATE ir_ui_view SET active=false WHERE id IN (SELECT res_id FROM ir_model_data WHERE module='portal_content' AND model='ir.ui.view' AND name=ANY(%s))",[names])
    cr.execute("UPDATE ir_cron SET active=false WHERE id IN (SELECT res_id FROM ir_model_data WHERE module='portal_content' AND model='ir.cron' AND name='cron_sync_google_reviews')")
    cr.commit()
print('WEBSITE_ROLLBACK_PREPARED='+json.dumps({'database':database,'qa_offers_archived':offers,'qa_counters_archived':counters,'qa_service_archived':qa_present,'original_sms_settings_restored':restore_sms,'newer_sms_configuration_preserved':not restore_sms,'business_rows_deleted':0}),flush=True)
