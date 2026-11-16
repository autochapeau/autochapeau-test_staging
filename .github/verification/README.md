# Video requirement verification

The user requested removing `tests` directories inside the modified addons after
validation. Their sources are retained here, outside addon directories, to make
post-deployment verification reproducible. Existing test sources retain their
original licenses.

The deployment workflow reads the module catalog without loading a registry,
installs only missing required feature addons, and upgrades the installed addons.
It preserves the distinction between installation and upgrade, then restarts the
staging service and runs:

1. `verify_staging.py`: installed versions, fields, contact selections, combined
   form views and actual invoice/journal QWeb HTML. Its transaction is rolled back.
2. `run_regression.py`: selected rollback-only Odoo TransactionCase suites for
   assets, contact references, analytics, fees/proof/cash custody, deferred service
   invoices and commission calculations/access/accounting. External Python network
   connections are denied while tests execute. No terminal or payment provider is
   contacted; provider tests use mocks.

Run only against the named TEST service/database. The script expects Odoo shell's
`env`, and `VIDEO_VERIFICATION_ROOT` must point to this directory. The workflow
copies this directory into the current Odoo container and sets the path.

Successful logs include `VIDEO_REQUIREMENTS_SMOKE=` and
`VIDEO_REQUIREMENTS_REGRESSION=` JSON markers. A failed assertion fails deployment
verification. Regression writes are rolled back; PostgreSQL sequence gaps and
temporary filestore garbage from test uploads can occur.

No business configuration or historical contact references/analytics are applied
automatically. Configure journal fee/accounts, deferred account, target allocation,
achievement tiers and optional discount adjustment through their forms. Historical
backfills have explicit, permission-checked actions.

For the 17.0.6.0.0 commission migration, `commission_upgrade_preservation.py`
runs before replacing the old checkout. It intentionally persists distinctly
labelled QA rules (product/service tiers, fixed and archived), a team target and
individual shares, three posted fictional invoices and a partial credit note on
`autochapeau_prod_test`. No user roles or existing business settings are changed.
The pre-upgrade baseline includes all existing rows in the audited commission,
legacy settlement, invoice, invoice-line, order and category tables. After restart,
row counts and hashes of original values must match. Salesperson assignments and
tier categories are compared semantically across the schema change. Baselines
and results remain under the persistent Odoo data directory in
`commission_upgrade_preservation/`. Logs include
`COMMISSION_PRESERVATION_BEFORE=` and `COMMISSION_PRESERVATION_AFTER=`.
This is a one-time legacy-schema audit; unrelated future deployments do not seed
more invoices once multi-salesperson rules are installed. It also permits the
explicitly named local rehearsal database `commission_preservation_legacy_20261109`.
