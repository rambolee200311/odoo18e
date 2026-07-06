# -*- coding: utf-8 -*-
{
    'name': "World Depot Bonded WMS",
    'summary': "荷兰保税仓管理模块 - Bonded Warehouse Management",
    'description': """
荷兰保税仓管理模块，覆盖从进口货代口岸端到陆路转运、保税仓入库、仓内监管、出库再转运的全链路。

核心功能:
- T1/B3海关申报管理 (SAD/C88格式)
- 到仓登记与封志核验 (gate.arrival)
- 保税入库/出库指令管理
- 保税库存属性与海关监管状态跟踪
- 核注核销记录与审计追溯
- 货值额度与担保管理
- 保税商品备案
- 监管日志 (不可篡改)
    """,
    'author': "World Depot B.V.",
    'website': "https://www.worlddepot.eu",
    'category': 'Warehouse/Bonded',
    'version': '1.0',
    'depends': [
        'base',
        'stock',
        'product',
        'mail',
        'worlddepot',
        'wd_immg',
    ],
    'data': [
        'security/bonded_security_groups.xml',
        'security/ir.model.access.csv',
        'security/bonded_record_rules.xml',
        'data/bonded_sequence.xml',
        'data/bonded_charge_seed_data.xml',
        'data/bonded_cron.xml',
        # Views
        'views/bonded_book_views.xml',
        'views/bonded_value_limit_views.xml',
        'views/bonded_customs_file_views.xml',
        'views/bonded_customs_file_line_views.xml',
        'views/bonded_product_views.xml',
        'views/gate_arrival_views.xml',
        'views/bonded_inbound_views.xml',
        'views/bonded_outbound_views.xml',
        'views/bonded_stock_views.xml',
        'views/bonded_verification_views.xml',
        'views/bonded_log_views.xml',
        'views/bonded_menus.xml',
        # Wizard
        'wizard/customs_file_create_from_handover_views.xml',
        'wizard/gate_arrival_create_views.xml',
        # Report
    ],
    'demo': [],
    'assets': {},
    'installable': True,
    'application': True,
    'license': 'LGPL-3',
}