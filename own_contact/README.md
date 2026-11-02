# Own Contact

Odoo 17 module. Install **Own Contact**, then open Settings > Users & Companies >
Users and use the **Contacts** tab (Settings administrators only). **Contact Access**
is a radio selection; saving it assigns exactly one mode:

- **Own Contact**: read/create/edit contacts assigned to the current user in
  Salesperson (`res.partner.user_id`). Unassigned contacts are hidden. Creation
  forces the current salesperson, including imports, batch creation and RPC.
  Reassignment and clearing Salesperson require manager access.
- **All Contacts (Manager)**: all contacts within existing company/security rules,
  with create/edit/delete and salesperson reassignment. Overrides Own Contact if
  both are selected. New contacts default to the manager unless an owner is supplied.
- **Default Access**: existing contact behavior remains unchanged, with neither
  contact access group assigned.

Existing permissions determine the initial radio selection; manager access takes
precedence if both old groups are present. Switching modes updates both groups in
one write. The previous Boolean fields remain available for API compatibility.

Ownership uses Salesperson, not Created By. Existing contacts are not reassigned.
Assign their Salesperson as a manager before enabling restrictions for a user.

All contact window actions add a mandatory Salesperson domain for Own Contact
users. This includes the Contacts app and custom Client/Supplier/Employee actions;
it preserves their original domains and cannot be removed as a search favorite.
Customer companies assigned to the current user are still listed.

Internal user partners and the user's allowed company partners remain readable so
Odoo can display user/company relations, but they are excluded from contact lists
unless assigned to the current user. This is a display restriction: system partners
remain accessible by direct record reads/links. These exceptions do not permit
editing other users/company records for ordinary Own Contact users. A user may
still update their own profile partner. Settings administrators keep write access
to internal user partners, so Odoo's delegated user model can save user permissions
and account details. This preserves the normal user-management ACLs and protected
fields; it grants no new user-management rights to contact managers or ordinary
salespeople. It does not widen contact lists or allow editing unrelated customers.
Child contacts require their own salesperson assignment; the parent's ownership
does not grant access. Superuser/sudo operations retain Odoo's standard bypass.
Other installed global restrictions (including Access Roles) still apply.

The administrator receives All Contacts (Manager) on installation. Permissions
are backed by groups, with conditional global record rules so broad group rules
cannot accidentally reveal another salesperson's contacts. Removing a permission
does not revoke access supplied by other modules.

## Validation

Use a disposable database to verify contact window action domains as an Own
Contact user, both normally and through sudo action loading; manager/unconfigured
users must keep the original domain. Also verify user/company partner reads and
user/company relation widgets, as well as automatic assignment and reassignment
protection. The module intentionally does not ship a tests folder.
