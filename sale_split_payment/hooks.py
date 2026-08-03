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
        "name": "Card Terminal",
        "code": "card_terminal",
        "sequence": 30,
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
]


def _find_journal(env, company, journal_type):
    Journal = env["account.journal"].sudo()
    domain = [("company_id", "=", company.id)]
    journal = Journal.search(domain + [("type", "=", journal_type)], limit=1)
    if not journal:
        journal = Journal.search(domain + [("type", "in", ("cash", "bank"))], limit=1)
    return journal


def _ensure_default_collection_methods(env):
    Method = env["sale.collection.method"].sudo()
    for company in env["res.company"].sudo().search([]):
        for template in DEFAULT_METHODS:
            values = {key: value for key, value in template.items() if key != "journal_type"}
            existing = Method.search(
                [
                    ("company_id", "=", company.id),
                    ("code", "=", values["code"]),
                ],
                limit=1,
            )
            journal = _find_journal(env, company, template["journal_type"])
            if existing:
                if not existing.journal_id and journal:
                    existing.journal_id = journal
                continue
            Method.create(
                {
                    **values,
                    "company_id": company.id,
                    "journal_id": journal.id,
                }
            )


def post_init_hook(env):
    _ensure_default_collection_methods(env)
