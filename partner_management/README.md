# Partner Management

## Unique new and changed mobile numbers (17.0.1.6.4)

New and changed mobile numbers are checked against all contacts, companies and archived records.
The existing normalization treats Saudi local, international and `00` formats
as equivalent, ignoring spaces and punctuation. Empty mobile fields are allowed.
The phone field is independent and can still match the mobile on the same contact.

Upgrade `partner_management` and restart Odoo to apply the change. Historical
duplicates remain unchanged and can still be edited without changing their
normalized mobile number. A new contact or a changed mobile cannot reuse them.
An internal `mobile_unique_key` is assigned to every new or changed mobile;
its SQL uniqueness also protects concurrent writes. Existing rows retain NULL
keys, so upgrades never rewrite, merge or delete legacy contacts. API callers
cannot disable the protection by setting the internal key.

The TEST deployment prepares the nullable column before scripts that load the
new registry, and retries module versions left pending by interrupted releases.

Review existing duplicate groups when needed:

```sql
SELECT mobile_normalized, array_agg(id ORDER BY id) AS contact_ids, count(*)
FROM res_partner
WHERE mobile_normalized IS NOT NULL
GROUP BY mobile_normalized
HAVING count(*) > 1;
```

Nine regression tests: `--test-enable --test-tags partner_mobile_unique`.
