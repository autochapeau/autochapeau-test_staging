# Sales Commission Studio — Odoo 17

Independent sales commission ledger, monthly regional targets and an OWL dashboard. Existing technician/employee settlements in `commission` remain separate; this addon reuses its service categories. Version 17.0.2.0.0 adds configurable expense/payable accruals; it does not create payroll or payments.

Version **17.0.4.0.0** includes an app icon, a comprehensive Arabic/English handbook, app-scoped right navigation and automatic regional visibility from Sales Team Leader.

## Configuration

1. Install `sales_region_commission` on the intended database in an offline maintenance window. Dependencies: `sale_management`, `account`, `commission` and their existing dependencies.
2. Open Settings / Users & Companies / Users and use the dedicated **Commission Access** tab. A system administrator selects No access, Salesperson, Region manager or Commission administrator. The duplicate generated selector in Access Rights is hidden. Existing users are not automatically granted access.
3. An administrator configures **Regions and teams** using CRM sales teams: Region → Subregion → Branch. Set the company, parent region and **Team Leader**, then assign salespeople as team members. With the **Region manager** commission role, a leader automatically receives that team and its descendants. **Commission manager** is optional additional scope. Leadership supplies scope but never grants a commission role.
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

Server ACLs and record rules apply to lists, forms, exports, pivots and dashboard aggregates. Salespeople see their own entries; regional managers additionally see teams they lead or explicitly manage and their descendants; administrators see entries across their allowed companies. Rules/targets/hierarchy configuration is restricted to administrators. Leadership, parent, company, archive-state and explicit-manager changes clear rule caches immediately. Ordinary membership is not regional access. Ledger edits, manual creation and deletion are prohibited for all normal users, including commission administrators.

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

System administrators manage commission roles from res.users / Commission Access. Managed regions can be assigned directly in this tab with company validation; selecting a team already assigned to another explicit commission manager transfers only that additional assignment, including descendants. Sales Team Leader remains independent. Removing a role preserves team assignments but revokes regional data access through the actual security groups. Other sales/accounting memberships remain separate. The read-only Historical accrual booking indicator requires both Commission Administrator and Accounting Administrator; no accounting rights are granted by this tab. The underlying groups and record rules remain authoritative, including changes made through the standard technical group management screens.

## Guide and right-hand navigation (17.0.3.0.0)

Open **Commission Studio / Guide & help**. The guide starts in Arabic and switches to English without leaving the page. Nine illustrated topics cover the overview, ledger, monthly targets, dated rules, region hierarchy, service categories, user access, accounting configuration and historical calculation. Each includes steps, a practical note, an expandable screenshot and an **Open screen** shortcut. The screenshot dialog uses Odoo's standard dialog and keyboard/focus behavior.

The sidebar and Open screen links use the current user's server-filtered menu tree. All app users can read all nine Guide chapters and their fictional examples. This documentation visibility does not expose real records or administrative screen access. Salespeople and region managers retain four workspace screens and Guide; commission administrators additionally see permitted configuration screens. **User access** requires Settings administration; **Accounting configuration** continues to require the existing accounting/settings permissions. Links use the normal Odoo menu/action service and keep unsaved-form protection. Menus explicitly retain their security groups. This interface does not grant model or accounting access.

The sidebar stays on the right across the app's native lists, forms, dashboard and guide, highlights the current screen, and can collapse to an icon rail. On small screens it uses a compact rail and an expandable panel. Other Odoo apps retain their standard navigation and layout. Regions and teams opens its list before the setup form.

`static/description/icon.png` is an original generated app icon, also used on the dashboard, sidebar and guide. `static/src/guide/screens/` contains nine genuine screenshots from a local QA copy with fictional salespeople, products, rates and amounts. These static examples are bundled with the addon and may be publicly served as Odoo static assets; **never replace them with production records, employee commissions or credentials**. Screenshots do not populate or change business data. Install/update the addon and refresh the browser to load the new menu and asset bundle.


## Automatic leadership and complete handbook (17.0.4.0.0)

Region manager scope is the union of Sales Team Leader teams, optional explicit Commission manager assignments, and descendants. The role is still required: a salesperson who leads a team continues to see only personal entries. Allowed and currently selected companies bound the scope, including shared teams; archived leadership teams retain historical reporting. The dashboard includes empty leadership roots. Leadership changes revoke the old leader immediately unless a separate explicit assignment remains. No leadership fields or historical commission snapshots are rewritten during upgrade. Ordinary authorized sales-team configuration continues to control Team Leader; ordinary commission users cannot assign themselves leadership.

The user tab distinguishes **Automatic teams from Team Leader** (read-only) from **Additional managed regions / teams** (optional). Clearing additional assignments does not remove automatic leadership. Removing the commission manager role revokes regional access even if team assignments remain.

All nine Guide chapters are readable by every app user. Each chapter has screen instructions, a field/metric reference, a worked example and practical FAQ; Overview also provides a setup checklist. Examples cover discounts and VAT, mixed product/service rates, dated rule changes, partial/FX refunds, target rollups, role and leader scope, debit/credit accruals, and historical retry. Only permitted screens have Open screen links. Static examples never query business data.
