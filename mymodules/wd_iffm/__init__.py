# -*- coding: utf-8 -*-

from . import models
from . import wizard
from . import controllers


def _init_workbench_lanes(env):
    """模块安装时初始化泳道数据"""
    Lane = env['operation.workbench.lane']
    lanes_data = [
        {'name': 'Forecast', 'code': 'waybill', 'sequence': 1},
        {'name': 'Handover', 'code': 'handover', 'sequence': 2},
        {'name': 'Clearance', 'code': 'clearance', 'sequence': 3},
    ]
    for lane_data in lanes_data:
        existing = Lane.search([('code', '=', lane_data['code'])], limit=1)
        if not existing:
            Lane.create(lane_data)
        else:
            existing.write({'sequence': lane_data['sequence'], 'name': lane_data['name']})
