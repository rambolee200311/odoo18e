# -*- coding: utf-8 -*-
{
    "name": "Advanced Record Picker",
    "summary": "通用 Many2one 高级记录选择器，支持多字段展示、筛选与选择",
    "description": """
Advanced Record Picker for Odoo 18.

主要能力：
1. 为标准 Many2one 字段提供高级记录选择模式
2. 支持基于 Picker Profile 配置多字段展示
3. 支持配置可筛选字段
4. 保留原 Many2one domain、context、ACL 和 record rules
5. 支持普通 Form View 和 Wizard
6. 选择记录后返回标准 Many2one record id

本模块定位为通用 Web UX 基础组件，不绑定具体业务模型。
    """,

    "author": "WD Dev",
    "website": "",
    "category": "Technical",
    "version": "18.0.1.0.0",

    "depends": [
        "base",
        "web",
    ],

    "data": [
        # security
        "security/ir.model.access.csv",

        # views
        "views/advanced_record_picker_profile_views.xml",
        "views/advanced_record_picker_menu.xml",
    ],

    "assets": {
        "web.assets_backend": [
            "wd_web_advanced_record_picker/static/src/**/*",
        ],
        "web.assets_unit_tests": [
            "wd_web_advanced_record_picker/static/tests/**/*",
        ],
    },

    "installable": True,
    "application": False,
    "auto_install": False,
    "license": "LGPL-3",
}