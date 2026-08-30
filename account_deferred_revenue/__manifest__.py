{
    "name": "Account Deferred Revenue",
    "summary": "Spread customer invoice revenue over a period with monthly recognition entries",
    "version": "17.0.1.0.0",
    "category": "Accounting",
    "author": "Wellknot",
    "license": "LGPL-3",
    "depends": ["account"],
    "data": [
        "data/ir_cron.xml",
        "views/res_config_settings_views.xml",
        "views/account_move_views.xml",
    ],
    "installable": True,
    "application": False,
}
