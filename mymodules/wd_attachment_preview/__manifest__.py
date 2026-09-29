# -*- coding: utf-8 -*-
{
    "name": "WD Attachment Preview",
    "summary": "Reusable attachment preview field for Odoo backend forms",
    "description": "Reusable attachment preview field for Many2many ir.attachment fields.",
    "author": "WD Dev",
    "category": "Technical",
    "version": "18.0.1.0.0",
    "depends": ["web"],
    "assets": {
        "web.assets_backend": [
            "wd_attachment_preview/static/src/fields/attachment_preview_field.js",
            "wd_attachment_preview/static/src/fields/attachment_preview_field.xml",
            "wd_attachment_preview/static/src/fields/attachment_preview_field.scss",
        ],
    },
    "installable": True,
    "application": False,
    "license": "LGPL-3",
}
