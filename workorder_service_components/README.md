# Service components by vehicle part

Odoo 17 — `workorder_service_components`, version `17.0.3.0.0`.

## Main categories, batch variants and replacement materials

1. In Inventory → Configuration → Product Categories, enable **Main Material Category** on each category offered for service materials. Selecting a category includes all of its descendants.
2. Define **Vehicle Parts** under Work Orders → Configuration or Inventory → Configuration → Products. Workshop managers can also create a part from the configuration form's selector.
3. Open a saved service template → Service Components → **Configure Multiple Variants**. Select the vehicle part and one or more variants of that template. Add materials with their main categories, positive default quantities and compatible units, then **Apply to Variants**.
4. Each variant receives independent `car.service.part` / `car.bom` records. Applying again updates the same product on the same part without duplicating it. Other existing materials are kept. Duplicate existing rows for that product require review before applying. Existing ungrouped materials remain available for manual assignment, as before.
5. Single-variant configuration remains available. Its material category is optional for compatibility with older recipes. New batch configuration requires a marked main category on every material.
6. New work-order snapshots carry the configured material category. The category stays fixed on the order. Product selection includes the category and all subcategories, and is validated on the server.
7. Workshop managers can replace categorized materials while the order is new, confirmed or in progress, until the material is issued. Service, vehicle part, source component and suggested quantity are retained. Actual quantity is retained; the product's default unit is selected and the old lot is cleared when changing products in the form. Review actual usage and choose a new lot/serial if needed. Finish issues the selected replacement product.
8. Issued materials remain locked. Older uncategorized lines retain their existing tag validation and confirmation locks. Upgrading does not rewrite historical orders or infer a material category for them. Configure categories on recipes for future orders.

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
