# -*- coding: utf-8 -*-
{
    "name": "Wallet Top-up",
    "version": "17.0.1.2.0",
    "summary": "Wallet top-up from Odoo + website HyperPay APIs",
    "category": "Sales",
    "author": "Wellknot",
    "depends": [
        "account",
        "sale",
        "appointment_management",
        "partner_management",
        "sale_split_payment",
        "portal_api",
    ],
    "data": [
        "security/ir.model.access.csv",
        "data/ir_sequence_data.xml",
        "wizard/wallet_topup_wizard_views.xml",
        "views/loyalty_exchange_log_views.xml",
        "views/res_partner_views.xml",
        "views/loyalty_card_views.xml",
        "views/wallet_topup_request_views.xml",
    ],
    "installable": True,
    "application": False,
    "auto_install": False,
    "license": "LGPL-3",
}
