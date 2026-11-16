def migrate(cr, version):
    # Determine the old effective method before the new default is initialized.
    # This changes neither categories/rates nor posted commission snapshots.
    cr.execute("ALTER TABLE sales_commission_rule ADD COLUMN IF NOT EXISTS calculation_method varchar")
    cr.execute("""UPDATE sales_commission_rule rule SET calculation_method = CASE
        WHEN EXISTS (SELECT 1 FROM sales_commission_tier tier WHERE tier.rule_id = rule.id)
        THEN 'tiers' ELSE 'fixed' END WHERE calculation_method IS NULL""")
