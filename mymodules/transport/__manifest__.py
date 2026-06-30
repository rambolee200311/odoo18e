# -*- coding: utf-8 -*-
{
    'name': "运输计划排期",
    'summary': "集装箱运输计划排期管理",
    'description': """
        运输计划排期模块
        ================
        * 左侧显示待安排的集装箱列表
        * 右侧显示日历，支持拖拽排期
        * 查看每日安排的集装箱数量
    """,
    'author': "Balance SHPG B.V.",
    'category': 'Logistics',
    'version': '1.0',
    'depends': ['base', 'web'],
    'data': [
        'security/ir.model.access.csv',
        'views/transport_plan_views.xml',
        'views/menus.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'transport/static/src/scss/transport_plan.scss',
            'transport/static/src/js/transport_plan/transport_plan.js',
            'transport/static/src/xml/transport_plan/transport_plan.xml',
        ],
    },
    'installable': True,
    'application': True,
    'license': 'LGPL-3',
}
