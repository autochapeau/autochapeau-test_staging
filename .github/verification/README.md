# Video requirement verification

The user requested removing `tests` directories inside the modified addons after
validation. Their sources are retained here, outside addon directories, to make
post-deployment verification reproducible. Existing test sources retain their
original licenses.

The deployment workflow upgrades the changed TEST addons, installs
`account_move_print` if needed, restarts the staging service, then runs:

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
