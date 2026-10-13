# -*- coding: utf-8 -*-
{
    "name": "WD Attachment Preview",
    "summary": "Reusable attachment preview field and image preview component",
    "description": "Provides a field widget for backend forms and a standalone component for PDA frontend with thumbnail preview and click-to-enlarge functionality.",
    "author": "WD Dev",
    "category": "Warehouse",
    "version": "18.0.1.0.0",
    "depends": ["web"],
    "assets": {
        "web.assets_backend": [
            "wd_attachment_preview/static/src/fields/attachment_preview_field.js",
            "wd_attachment_preview/static/src/fields/attachment_preview_field.xml",
            "wd_attachment_preview/static/src/fields/attachment_preview_field.scss",
            "wd_attachment_preview/static/src/components/image_preview_component.js",
            "wd_attachment_preview/static/src/components/image_preview_component.xml",
            "wd_attachment_preview/static/src/components/image_preview_component.scss",
        ],
    },
    "installable": True,
    "application": False,
    "license": "LGPL-3",
}
