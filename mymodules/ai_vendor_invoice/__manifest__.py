# © 2024 Wukong Digital. License LGPL-3.
# Architecture red-lines (see tdd_wd_ai_vendor_invoice_v1.4.md §1):
#   - manifest depends MUST NOT include the deprecated synchronous import module (T-016)
#   - AI HTTP calls must never hold a DB row-lock (T-002)
{
    "name": "WD AI Vendor Invoice",
    "version": "18.0.1.0.0",
    "category": "Accounting/Accounting",
    "summary": "AI-assisted vendor invoice recognition and import",
    "author": "Wukong Digital",
    "license": "LGPL-3",
    "depends": ["account", "contacts", "queue_job"],
    "data": [
        "security/groups.xml",
        "security/ir.model.access.csv",
        "security/record_rules.xml",
        "data/system_config_data.xml",
        "data/ir_cron.xml",
        "views/diagnostic_views.xml",
        "views/import_task_views.xml",
        "views/config_views.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "ai_vendor_invoice/static/src/owl/review_dialog.js",
            "ai_vendor_invoice/static/src/owl/review_dialog.xml",
        ],
    },
    "installable": True,
    "application": True,
    "auto_install": False,
}
