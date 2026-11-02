# Own Contact

Odoo 17 module. Install **Own Contact**, then open Settings > Users & Companies >
Users and use the **Contacts** tab (Settings administrators only).

- **Own Contact**: read/create/edit contacts assigned to the current user in
  Salesperson (`res.partner.user_id`). Unassigned contacts are hidden. Creation
  forces the current salesperson, including imports, batch creation and RPC.
  Reassignment and clearing Salesperson require manager access.
- **All Contacts (Manager)**: all contacts within existing company/security rules,
  with create/edit/delete and salesperson reassignment. Overrides Own Contact if
  both are selected. New contacts default to the manager unless an owner is supplied.
- Neither selected: existing contact behavior remains unchanged.

Ownership uses Salesperson, not Created By. Existing contacts are not reassigned.
Assign their Salesperson as a manager before enabling restrictions for a user.

Internal user partners and the user's allowed company partners remain readable so
Odoo can display user/company relations. These exceptions do not permit editing
other users/company records. A user may still update their own profile partner.
Child contacts require their own salesperson assignment; the parent's ownership
does not grant access. Superuser/sudo operations retain Odoo's standard bypass.
Other installed global restrictions (including Access Roles) still apply.

The administrator receives All Contacts (Manager) on installation. Permissions
are backed by groups, with conditional global record rules so broad group rules
cannot accidentally reveal another salesperson's contacts. Removing a permission
does not revoke access supplied by other modules.

## Validation

Run on a disposable Odoo test database with dependencies available:

```powershell
python odoo-bin -c odoo.conf -d own_contact_test -i own_contact --test-enable --test-tags /own_contact --stop-after-init --without-demo=all
```

Tests cover search/direct access, batch/default assignment, reassignment protection,
manager precedence, system record exceptions, user-tab permissions and escalation,
unconfigured users, permissive group rules, and multi-company boundaries.
