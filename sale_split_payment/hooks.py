DEFAULT_METHODS = [
    {
        "name": "Cash",
        "code": "cash",
        "sequence": 10,
        "processing_type": "manual",
        "require_reference": False,
        "journal_type": "cash",
    },
    {
        "name": "Bank Transfer",
        "code": "bank_transfer",
        "sequence": 20,
        "processing_type": "manual",
        "require_reference": True,
        "journal_type": "bank",
    },
    {
        "name": "Card",
        "code": "card",
        "sequence": 30,
        "processing_type": "manual",
        "require_reference": True,
        "journal_type": "bank",
    },
    {
        "name": "Card Terminal",
        "code": "card_terminal",
        "sequence": 35,
        "processing_type": "terminal",
        "require_reference": False,
        "journal_type": "bank",
    },
    {
        "name": "Tabby",
        "code": "tabby",
        "sequence": 40,
        "processing_type": "tabby",
        "require_reference": False,
        "journal_type": "bank",
    },
    {
        "name": "Tabby Manual",
        "code": "tabby_manual",
        "sequence": 45,
        "processing_type": "manual",
        "require_reference": True,
        "journal_type": "bank",
    },
    {
        "name": "Tamara",
        "code": "tamara",
        "sequence": 50,
        "processing_type": "manual",
        "require_reference": True,
        "journal_type": "bank",
    },
    # Same labels/codes as portal_api payment.method (Collect Payment inside Odoo).
    {
        "name": "Hyper Pay",
        "code": "hyperpay",
        "sequence": 60,
        "processing_type": "manual",
        "require_reference": True,
        "journal_type": "bank",
    },
    {
        "name": "Wallet",
        "code": "wallet",
        "sequence": 70,
        "processing_type": "manual",
        "require_reference": False,
        "journal_type": "bank",
    },
    {
        "name": "Qitaf points",
        "code": "qitaf",
        "sequence": 80,
        "processing_type": "manual",
        "require_reference": False,
        "journal_type": "bank",
    },
    {
        "name": "My Rajhi Points",
        "code": "rajhi",
        "sequence": 90,
        "processing_type": "manual",
        "require_reference": False,
        "journal_type": "bank",
    },
    {
        "name": "myList",
        "code": "mylist",
        "sequence": 100,
        "processing_type": "manual",
        "require_reference": False,
        "journal_type": "bank",
    },
]


def _find_journal(env, company, journal_type):
    """Prefer a posted bank/cash journal that has an outstanding receipts account."""
    Journal = env["account.journal"].sudo()
    domain = [
        ("company_id", "=", company.id),
        ("type", "=", journal_type),
    ]
    journals = Journal.search(domain, order="sequence, id")
    for journal in journals:
        if journal.inbound_payment_method_line_ids:
            return journal
    if journals:
        return journals[:1]
    return Journal.search(
        [("company_id", "=", company.id), ("type", "in", ("cash", "bank"))],
        order="sequence, id",
        limit=1,
    )


def _default_payment_method_line(journal):
    if not journal:
        return journal.env["account.payment.method.line"]
    lines = journal.inbound_payment_method_line_ids
    # Prefer an inbound line that posts to the journal's outstanding receipts account.
    outstanding = journal.company_id.account_journal_payment_debit_account_id
    if outstanding:
        matched = lines.filtered(lambda line: line.payment_account_id == outstanding)
        if matched:
            return matched[:1]
    return lines[:1]


def _ensure_default_collection_methods(env):
    Method = env["sale.collection.method"].sudo()
    for company in env["res.company"].sudo().search([]):
        for template in DEFAULT_METHODS:
            values = {
                key: value
                for key, value in template.items()
                if key != "journal_type"
            }
            existing = Method.search(
                [
                    ("company_id", "=", company.id),
                    ("code", "=", values["code"]),
                ],
                limit=1,
            )
            journal = _find_journal(env, company, template["journal_type"])
            method_line = _default_payment_method_line(journal)

            if existing:
                updates = {}
                # Restore Tabby API if a previous migrate forced it to manual.
                if (
                    values["code"] == "tabby"
                    and existing.processing_type != "tabby"
                ):
                    updates["processing_type"] = "tabby"
                    updates["require_reference"] = False
                    updates["name"] = values["name"]
                if not existing.journal_id and journal:
                    updates["journal_id"] = journal.id
                target_journal = (
                    journal
                    if updates.get("journal_id")
                    else existing.journal_id or journal
                )
                if target_journal and (
                    not existing.payment_method_line_id
                    or existing.payment_method_line_id.journal_id != target_journal
                ):
                    line = _default_payment_method_line(target_journal)
                    if line:
                        updates["payment_method_line_id"] = line.id
                if updates:
                    existing.write(updates)
                continue

            Method.create(
                {
                    **values,
                    "company_id": company.id,
                    "journal_id": journal.id if journal else False,
                    "payment_method_line_id": method_line.id if method_line else False,
                }
            )


def post_init_hook(env):
    _ensure_default_collection_methods(env)
