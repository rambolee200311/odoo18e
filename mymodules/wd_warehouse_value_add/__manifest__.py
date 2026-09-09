# -*- coding: utf-8 -*-
{
    'name': 'Warehouse Value Add',

    'summary': (
        '仓库贴标、缠膜等库内增值作业登记，'
        '支持 Web 电脑端和 PDA 手持端录单'
    ),

    'description': """
Warehouse Value Add
===================

仓库库内增值作业登记模块，用于记录贴标、缠膜、换箱、打托、
盘点等现场实际发生的库内增值作业。

业务规则
--------

1. 一张作业单只对应一个操作员。
   不同操作员分别建立自己的作业单。

2. 同一个入库订单、出库订单或其他业务订单，
   可以关联多张库内增值作业单。

3. 一张作业单可以登记一条或多条作业明细，
   支持一单多作业。

4. 作业明细使用统一的“数量/工时”字段。
   系统根据所选操作类型自动带出对应计量单位，
   单位无需仓管人工填写。

5. 关联单据号支持扫码录入或手工输入，
   系统识别并绑定对应业务单据。

6. 图片、视频作为作业凭证，可根据现场情况选择上传，
   为非必填项，并支持多个附件。

7. Web 电脑端用于办公录单和历史单据查询。

8. PDA 手持端用于仓库现场快速录单。
   PDA 操作员默认取当前登录人员并只读展示，
   操作人员登记本人实际完成的作业。

9. 草稿状态允许保存和继续修改。
   草稿允许暂时没有作业明细，
   但提交时必须至少存在一条有效作业明细。

10. 单据提交后核心业务字段锁定，
    不允许直接修改；错误数据后续通过更正流程处理。

11. 作业单号、新增时间、提交人、提交时间等系统字段
    均由系统自动维护，人工不可修改。

12. 本模块记录仓库增值作业事实。
    当前版本不包含增值作业计费、结算等财务业务。
    """,

    'author': 'WD Dev',
    'website': '',
    'category': 'Warehouse',
    'version': '1.0.0',

    'depends': [
        'base',
        'mail',
        'web',
        'worlddepot',
    ],

    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',
        'data/ir_sequence_data.xml',
        'views/vas_operation_type_views.xml',
        'views/vas_order_views.xml',
        'views/vas_frontend_actions.xml',
        'views/vas_menus.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'wd_warehouse_value_add/static/src/js/vas_dashboard.js',
            'wd_warehouse_value_add/static/src/js/vas_pda_action.js',
            'wd_warehouse_value_add/static/src/xml/vas_dashboard.xml',
            'wd_warehouse_value_add/static/src/xml/vas_pda_action.xml',
            'wd_warehouse_value_add/static/src/scss/vas_pda_action.scss',
        ],
        'web.assets_tests': [
            'wd_warehouse_value_add/static/tests/vas_pda_action_tests.js',
        ],
    },

    'installable': True,
    'auto_install': False,
    'application': True,

    'license': 'LGPL-3',
}