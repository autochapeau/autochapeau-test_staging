# Maintenance requests

New requests start on a confirmed sale order. Select its service, an original
work order service whose materials were issued, and one or more vehicle parts.
Additional problem notes are optional. Services repeated on multiple sale lines
require an unambiguous original mapping before a request can be submitted.

The request snapshots the selected parts' completed material deliveries. Quantity
uses the material's stock UoM; unit cost comes from the original stock valuation
layers, including valuation adjustments present when the request is created.
Current product cost and current service recipes are never cost fallbacks.
Missing original valuation stops submission. Request materials are immutable.
Existing requests retain their historical values.

Quality retains the customer/technician/supplier decision and cost allocation.
Confirmation creates a confirmed maintenance sale order with `related_sale_id`
pointing to the exact original order. It serializes confirmation to prevent
duplicate orders and entries. The appointment still needs to be saved separately.

The repair work order snapshots only the selected original materials and parts,
even if the service recipe subsequently changes or is deleted. Actual repair
usage remains editable before issue through the normal workshop flow. Its stock
delivery does not retrospectively change the original claim's allocated cost.
For flagged tint services, configure **Tint Glass Type** on each vehicle part;
the original sale's matching glass/tint detail is copied once per glass.

Technician allocation is an accounting charge, not an automatic payroll deduction.
Supplier attribution does not create a supplier debit note or recovery claim.

`tests/test_maintenance_parts.py` exercises selection, issued quantities,
historical valuation, UoM conversion, access, immutable snapshots, repair scope,
recipe changes, tint mapping, all three causes, accounting and repeated approval.
The deployment regression runner includes this suite and rolls its records back.
