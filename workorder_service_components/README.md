# Service components by vehicle part

Odoo 17 â€” `workorder_service_components`, version `17.0.4.0.0`.


## Film measurements, size variants and category-only recipes

- The batch configuration accepts multiple **Vehicle Parts**. Leave the list empty for whole-service materials such as paint. Each part/variant gets independent records. Existing ungrouped rows remain read-only reference.
- A material can specify **Material Category** without a product. The work order snapshots the category, dimensions, quantity unit and allowed brands. Choose the actual product before Finish, including on zero-use configured rows. Appointment/upsell loaders only preload concrete products; work-order synchronization adds category placeholders once per service task.
- Use **Quantity** for litres, millilitres, kilograms, etc. Set a positive default quantity and the intended unit. Category-only rows retain that unit when a compatible product is selected; incompatible unit categories are rejected.
- Use **Film Dimensions** for film rolls. Enter standard length and width in inches. Actual dimensions start from the standard and can be edited until issue. The product supplies **Film Width (in)** and **Roll Length (m)**. Roll length means the physical length represented by ONE product stock unit (15 for one 15-m roll, 1 when stocked in metres). Different film widths should have separate product variants.
- Film stock must use a unit allowing fractions (rounding below 1). Consumption in base stock units is `length_in * width_in * 0.0254 / (film_width_in * roll_length_m)`. It is rounded UP to the coarser of the line unit's rounding and Odoo's **Product Unit of Measure** decimal precision. At the usual two decimals, 0.00847 roll consumes 0.01 roll. Increase both the unit precision and that decimal precision if finer stock accounting is needed. The displayed quantity and stock movement agree.
- **Optional Size Overrides** applies different quantities, units and dimensions to each selected variant (Small/Medium/Large/XL). Each override applies to all batch materials for that variant. For different recipes by material or part, edit the resulting saved part directly.
- Set total car length/width budgets and the part tolerance on each service variant (or the service template when it has one variant). Defaults are a 5-inch part tolerance and no overall limit. Budgets are snapshotted per service occurrence: compare the SUM of part lengths and SUM of part widths, not the car's physical body dimensions. The order also shows combined metres and square metres. An actual dimension exactly 5 inches above standard is allowed without a part warning; above that shows a warning. Exceeding a nonzero total budget also warns. These are advisory warnings; an impossible cut wider than the film is rejected.
- Define **Material Brands** in Work Orders → Configuration and assign a brand to each raw product. **Allowed Brands** limits the brands for a recipe. On the order, select **Brand** first to filter products by brand AND material category; empty allowed brands permits any brand. Server validation enforces the same restrictions. Existing products are not guessed into brands from their names.
- Historical order quantities are retained. New-order standards, brands, film size and car budgets are snapshots. Reconfiguring a service or raw material does not rewrite them. Selecting a replacement film loads that product's own width/length and recalculates consumption. Issued measurements, standards, allowed brands and stock links stay locked; QA uses the selected material and actual consumption.

## Reference-only legacy materials

Only materials assigned to a configured vehicle part are operational service components. **Existing Ungrouped Materials** is read-only historical reference: its rows do not populate new work orders, appointments, upsells, QA checklists or material defaults. Deleting configured parts/materials cannot reactivate those ungrouped rows. Existing work-order snapshots and stock movements are retained. Configure materials under vehicle parts to use them on future orders.

## Branch material availability

### Appointment work orders

- Confirm an appointment to create its work order with service parts and material requirements. The selected product and brand stay blank. Separately sold stock products retain their normal delivery.
- After Check-in, the workshop manager assigns technicians and confirms the work order. Confirmation creates one preparation request per service with configured materials. Assign a **Workshop Materials Preparer** as the warehouse default or on the service task. The assigned user opens **Materials to Prepare** and sees the service, parts, and material inputs.
- Choose an approved brand and stock product for each required part. Check the branch balance and enter the actual measurements or quantity. Mark the request **Materials Prepared**. A workshop manager can complete or reopen a request before starting the order. Services without materials do not create requests.
- At **Start**, the balance is checked again and the assigned technicians can use **My Workshop Tasks**. Material preparation does not reserve or issue stock. Existing Finish logic records actual consumption and checks availability again.
- Assign **Quality Reviewers** and **Final Workshop Checks** on each workshop. Add **Task Quality Checks** on service variants or use the existing product features. Use **Skip Task Quality** on a variant that does not need it. Reviewers use **Pending Task Quality**. Once tasks and required reviews are done, the workshop manager approves the separate general inspection.
- The staged flow applies to newly created appointment work orders. Existing records keep their saved selections and the workflow they started with.

The work order's Products tab shows **Available in Branch** in the row's UoM. This is unreserved stock under the branch warehouse's stock location, including its sublocations. It excludes other branches and follows the work order's company. A selected lot/serial restricts the balance to that exact lot. The optional **Material Warehouse** column identifies the warehouse used.

Choosing a material or changing its used quantity, unit or lot displays an **Insufficient Branch Stock** warning when stock is insufficient. The **Stock Warning** column and highlighted rows retain the warning on saved orders. Demand includes other pending rows for the same product on the order (for a selected lot, other rows using that lot), so repeated parts cannot each assume the entire balance is available. Issued rows no longer contribute to pending demand.

These are advisory checks: they do not reserve stock or block saving. Reload the order to refresh balances changed by other operations. Finish blocks shortages by default. A stock manager can enable **Allow Workshop Material Issue with Insufficient Stock** on the branch warehouse to finish tasks and record actual consumption even when this creates a negative balance. Missing branch/warehouse configuration is explained in the warning column without preventing historical orders from opening; legacy consumables do not produce stock shortage warnings.

## Main categories, batch variants and replacement materials

1. In Inventory â†’ Configuration â†’ Product Categories, enable **Main Material Category** on each category offered for service materials. Selecting a category includes all of its descendants.
2. Define **Vehicle Parts** under Work Orders â†’ Configuration or Inventory â†’ Configuration â†’ Products. Workshop managers can also create a part from the configuration form's selector.
3. Open a saved service template â†’ Service Components â†’ **Configure Multiple Variants**. Select the vehicle part and one or more variants of that template. Add materials with their main categories, positive default quantities and compatible units, then **Apply to Variants**.
4. Each variant receives independent `car.service.part` / `car.bom` records. Applying again updates the same product on the same part without duplicating it. Other existing materials are kept. Duplicate existing rows for that product require review before applying. Existing ungrouped materials remain visible as read-only reference.
5. Single-variant configuration remains available. Its material category is optional for compatibility with older recipes. New batch configuration requires a marked main category on every material.
6. New work-order snapshots carry the configured material category. The category stays fixed on the order. Product selection includes the category and all subcategories, and is validated on the server.
7. Workshop managers can replace categorized materials while the order is new, confirmed or in progress, until the material is issued. Service, vehicle part, source component and suggested quantity are retained. Actual quantity is retained; the product's default unit is selected and the old lot is cleared when changing products in the form. Review actual usage and choose a new lot/serial if needed. Finish issues the selected replacement product.
8. Issued materials remain locked. Older uncategorized lines retain their existing tag validation and confirmation locks. Upgrading does not rewrite historical orders or infer a material category for them. Configure categories on recipes for future orders.

## Configuration and operation

1. A workshop manager defines reusable **Vehicle Parts** under **Work Orders â†’ Configuration**.
2. Open a saved service product, then **Service Components**. Add a vehicle part and open its form to enter multiple storable products, default quantities and compatible units. On a template with multiple variants, select the applicable service variant.
3. Existing ungrouped BOM materials remain visible under **Existing Ungrouped Materials** for reference only. Configure the required materials under vehicle parts for future orders. No historical BOM or quantity is deleted by the upgrade.
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
