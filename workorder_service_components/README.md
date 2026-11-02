# Service components by vehicle part

Odoo 17 — `workorder_service_components`, version `17.0.2.0.0`.

## Configuration and operation

1. A workshop manager defines reusable **Vehicle Parts** under **Work Orders → Configuration**.
2. Open a saved service product, then **Service Components**. Add a vehicle part and open its form to enter multiple storable products, default quantities and compatible units. On a template with multiple variants, select the applicable service variant.
3. Existing BOM materials remain available under **Existing Ungrouped Materials**. Assign their **Service Part** to reuse them; do not add the same material again. No historical BOM or quantity is deleted by the upgrade.
4. Saving a new work order or confirming it snapshots the service's parts and materials into **Parts & Products**. Appointment and upsell material rows are adopted instead of duplicated. Repeated service tasks have independent material sets.
5. Confirm the work order after check-in, then press **Start Services**. The existing task Start/Pause controls remain available.
6. Adjust **Used Quantity** while working. **Suggested Quantity** preserves the configured quantity. Select **Lot / Serial** when applicable; show this optional column from the list's column selector. Each serial-numbered row must consume one base unit.
7. Press **Finish Services**, or finish an individual service task. The system reserves and completes a delivery from the branch warehouse to Customers, using actual quantities and selected units/lots. Zero-used rows do not move stock. Service tasks continue through the existing QA workflow.
8. Stock users can inspect **Material Deliveries** from the work order. Separately sold products remain on the original delivery and are not automatically issued by Finish.

## Inventory integrity

- Finishing requires the work order to be in progress and its task to have started.
- Stock must be available; partial reservations and missing/mismatched lots stop the operation. A failed finish rolls back task completion and material delivery together.
- Per-order row locks coordinate finishing with actual-quantity edits. Stock reservation uses Odoo's reservation mechanism.
- One move per material row preserves the vehicle-part allocation even when two parts use the same product.
- Issue flags and stock-move links are controlled by the Finish operation, not by editable form fields.
- Repeated Finish or QA rework cannot issue the original materials again. Existing replacement deliveries from QA remain separate.
- Issued materials cannot be edited/deleted. Corrections require normal inventory returns or replacement deliveries.
- Existing open orders adopt their existing material quantities rather than today's BOM. An already completed initial delivery is recognized to avoid double consumption. Reserved legacy deliveries or ambiguous repeated legacy services require review.
- Tracked materials use their selected lot/serial. Variant-specific recipes remain separate.

## Upgrade

Update the addon and upgrade `workorder_service_components` on the intended database using the normal Odoo deployment process:

```sh
python odoo-bin -c /path/to/odoo.conf -d DATABASE -u workorder_service_components --stop-after-init
```

Dependencies include `workorder_task_quality` and its existing time-tracking dependencies, so Finish preserves task timing and quality checks. Restart the regular Odoo service after the upgrade. No production deployment is performed by the development tests.

## Tests

```sh
python odoo-bin -c /path/to/test.conf -d TEST_DATABASE -u workorder_service_components --test-enable --test-tags /workorder_service_components --stop-after-init --no-http
```

The transaction tests exercise configuration forms, combined inherited views, actual work-order confirmation, snapshots, legacy adoption, repeated services, actual usage, UoM conversion, shortages and rollback, zero usage, lot/serial tracking, QA rework, permissions and issued-material locks.
