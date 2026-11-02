# Sales Commission Studio — Odoo 17

Independent sales commission ledger, monthly regional targets and an OWL dashboard. Existing technician/employee settlements in `commission` remain separate; this addon reuses its service categories. Version 17.0.2.0.0 adds configurable expense/payable accruals; it does not create payroll or payments.

## Configuration

1. Install `sales_region_commission` on the intended database in an offline maintenance window. Dependencies: `sale_management`, `account`, `commission` and their existing dependencies.
2. Open Settings / Users & Companies / Users and use the dedicated **Commission Access** tab. A system administrator selects No access, Salesperson, Region manager or Commission administrator. The duplicate generated selector in Access Rights is hidden. Existing users are not automatically granted access.
3. An administrator configures **Regions and teams** using CRM sales teams: Region → Subregion → Branch. Set the company, parent region and **Commission manager**, then assign salespeople as team members. `Commission manager` explicitly determines regional visibility; the normal Team Leader field alone does not grant commission access.
4. Configure dated rules per salesperson: exact `Product Category` for goods, existing `Commission Category` for services (VIP / Platinum / Gold, etc.). Assign service categories on product variants using the existing field. Rates accept 0–100%; overlapping active rules for the same company, person and category are rejected. Archive used rules rather than deleting them.
5. Set monthly targets per team/company, using the first day of each month. Targets are monitoring goals and **do not gate or change commission rates**. Parent and child targets are not added twice in the overview. A salesperson sees their own contribution against their accessible team target, not teammates' sales.

## Calculation policy

- Only posted customer invoices and customer credit notes generate entries. Draft invoices, quotations and vendor bills do not earn commissions. There is one snapshot per product invoice line; tax, payment-term and section lines are excluded.
- Attribution comes from the original sale order, not the invoice salesperson. Multiple orders on one invoice line must agree on salesperson, team and company. Missing/ambiguous attribution or a missing rule produces a visible **Needs review** entry with zero commission; posting is not blocked by a missing commission rule.
- Invoice base is the signed, posted untaxed line balance in company currency, after discounts. A copied rate and category label preserve the original calculation when rules/products change later.
- Credit notes created through Odoo's reversal flow retain an exact source-line reference, including repeated products. Partial credits use the original rate and proportional original commission. Full foreign-currency reversals reverse the original commission even if exchange rates changed; net invoiced reporting still uses posted company-currency balances. Older/manual credit notes use a unique matching original product/sale line when possible; ambiguous or absent links require review.
- Resetting an invoice to draft removes its snapshot. Reposting calculates it again using the then-applicable dated rule. Reset linked posted credit notes before resetting their original invoice. Cancelling removes the corresponding entries. Normal accounting locks and fiscal validations remain in force.
- **Calculate posted commissions** explicitly processes historical posted invoices in a selected company/date range (maximum 500 invoices per batch). It calculates missing entries and optionally retries review entries, while preserving already calculated snapshots. Process original invoices before credit notes from a later period. No historical financial documents are changed, and no backfill runs automatically on install.

## Access and dashboard

Server ACLs and record rules apply to lists, forms, exports, pivots and dashboard aggregates. Salespeople see their own entries; regional managers additionally see descendants of their assigned teams; administrators see entries across their allowed companies. Rules/targets/hierarchy configuration is restricted to administrators. Region reassignment clears rule caches immediately. Ledger edits, manual creation and deletion are prohibited for all normal users, including commission administrators.

The dashboard includes month/team filters, net invoiced revenue, credit-note reductions, net commission, targets, achievement, daily activity, person-level totals and review counts. Ledger drilldowns preserve the selected scope. Loading, empty and error states are supported. Responsive layouts use CSS with logical properties for RTL compatibility. Accounting document access continues to depend on the user's normal accounting permissions.

## Validation

Run on a disposable restored database with outbound integrations isolated:

```sh
python odoo-bin -c test.conf -d TEST_DATABASE -i sales_region_commission --test-enable --test-tags /sales_region_commission --stop-after-init --no-http
```

The transaction suite covers posted net amounts, discounts/tax, service categories, effective dates, partial/full and repeated-product refunds, exchange-rate changes, reset/repost, idempotency, missing rules, ambiguous attribution, company isolation, role-based searches/dashboard aggregates, immediate manager revocation, write protection, targets, invalid hierarchy and historical retry. Test journals disable EDI only on their own fixtures; real fiscal settings are not modified.

Runtime test configurations, restored databases, local QA accounts and preview invoices belong under `outputs/`, outside the addon. Never deploy those fixtures or use sample test rates as business commission policy.


## Accounting accruals (17.0.2.0.0)

Accounting / Configuration / Settings / Sales commission accruals contains per-company activation, a miscellaneous journal, a debit expense account and a credit liability/payable account. Activation defaults to off. The journal and both accounts must be valid, active, same-company and in company currency. Expense and liability accounts must differ. A shortcut is also available in Commission Studio for authorized finance/settings users.

When enabled, posting a customer invoice snapshots its commission and posts a balanced miscellaneous entry: debit commission expense, credit commission payable. Lines retain the salesperson's partner. Review entries and zero commissions are never booked. Repeated booking does not create duplicates; invoice-row locks serialize booking.

Credit notes debit the original payable and credit the original expense for the refunded commission. Original journal/account snapshots are used even if settings change or future accruals are disabled. An original commission that was never booked cannot create a negative liability on refund.

The ledger shows Accounting status and its accrual entry. The invoice's Commission accounting tab preserves accruals and reversals. Resetting/cancelling the source posts a reversal dated today and keeps the original journal entry. Reposting creates a fresh accrual. Normal fiscal locks and accounting validation apply; failures roll back the operation. Generated entries and financial lines cannot be manually edited, reset, reversed or deleted. Standard payable reconciliation remains supported.

Historical calculation never posts accruals silently. Booking historical pending entries requires both Commission Administrator and Accounting Administrator roles, with company configuration enabled. Book original commissions before old credit notes. Upgrading preserves v1 commission values and leaves accounting disabled until configured. Accruals recognize liabilities only; normal payment and reconciliation remain separate.


## Dedicated user access tab (17.0.2.1.0)

System administrators manage commission roles from res.users / Commission Access. Managed regions can be assigned directly in this tab with company validation; selecting a team already assigned to another manager transfers that management scope, including descendants. Removing a role preserves team assignments but revokes regional data access through the actual security groups. Other sales/accounting memberships remain separate. The read-only Historical accrual booking indicator requires both Commission Administrator and Accounting Administrator; no accounting rights are granted by this tab. The underlying groups and record rules remain authoritative, including changes made through the standard technical group management screens.
