# -*- coding: utf-8 -*-
{
    "name": "Journal Entry Report | Journal Entry Print | Journal Entry | Print Journal entry",
    "version": "17.0.1.0.0",
    "category": "Accounting",
    "summary": "Generate clean and professional Journal Entry PDF reports with dynamic company branding.",
    "description": """
Journal Entry Report for Odoo
Journal Entry Print | Journal Entry
=============================
This module adds a professional printable PDF report for Journal Entries (account.move).

Key Features:
--------------
- Prints directly from Journal Entries list or form view.
- Displays header details (Journal, Date, Number, Reference, Company, Partner).
- Includes line details: Account, Label, Debit, Credit, Amount Currency, Analytic Distribution.
- Computes totals for Debit and Credit automatically.
- Adopts the company's color theme dynamically.
- Compatible with Odoo 17 Accounting module.

Developed by Ahson Mahmood
--------------------------
For professional support and customization:
- Email: ahsonmahmood113.am@gmail.com
- LinkedIn: https://www.linkedin.com/in/ahsonmahmood/
""",
    "author": "Ahson Mahmood",
    "website": "https://www.linkedin.com/in/ahsonmahmood/",
    "license": "LGPL-3",
    "depends": ["base", "account"],
    "data": [
        "report/journal_entry_report_templates.xml"
    ],
    "assets": {},
    "images": ["static/description/main_screenshot.png"],
    "installable": True,
    "application": False,
    "auto_install": False,
}
