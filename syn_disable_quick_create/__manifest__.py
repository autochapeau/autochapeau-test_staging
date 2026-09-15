# -*- coding: utf-8 -*-
{
    "name": "Disable Quick Create",
    "version": "17.0.1.1.0",
    "summary": "Disable all Create / Create & Edit / Quick Create buttons for Many2One and Many2Many fields",
    "category": "Custom",
    'author': 'Synable Technology',
    'website': 'https://www.synabletech.com',
    "depends": ["web"],
    "assets": {
        "web.assets_backend": [
            "syn_disable_quick_create/static/src/js/disable_relational_create.js",
        ],
    },
    "installable": True,
    "application": False,
    "auto_install": False,
    "license": "LGPL-3",
}
