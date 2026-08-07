# -*- coding: utf-8 -*-
"""pickup.plan — 计划链路子单据 单元测试
核心规则: Sprint50 起显式 state 状态机（draft→scheduled→reserved→executing→finished）
"""
from odoo.tests.common import TransactionCase
from odoo.exceptions import UserError


class TestPickupPlan(TransactionCase):
    """pickup.plan: 双形态cargo_type + 四场景destination_type + 无状态机生命周期 + IFFM引用"""

    def setUp(self):
        super().setUp()
        self.wh1 = self.env['stock.warehouse'].create({'name': 'WH1', 'code': 'WH1'})
        self.wh2 = self.env['stock.warehouse'].create({'name': 'WH2', 'code': 'WH2'})
        self.partner = self.env['res.partner'].create({'name': 'Test Customer'})
        self.partner = self.env['res.partner'].create({'name': 'Test Customer'})
        self.carrier = self.env['res.partner'].create({
            'name': 'Test Carrier', 'is_carrier': True,
        })
        try:
            waybill = self.env['world.depot.waybill'].create({'name': 'Test'})
            self.iff_req = self.env['import.pickup.requirement'].create({
                'waybill_id': waybill.id, 'pickup_scene': 'to_our_warehouse',
            })
            self.env['world.depot.charge.item'].create({'item_name': 'Transport Fee'})
        except Exception:
            self.iff_req = None
        self.default_req = self.env['tlmp.transport.request'].create({
            'request_type': 'plan_driven',
            'destination_type': 'warehouse',
            'cargo_type': 'container',
            'warehouse_id': self.wh1.id,
        })

    def _mk_plan(self, **kw):
        vals = {
            'cargo_type': 'container',
            'destination_type': 'warehouse',
            'warehouse_id': self.wh1.id,
            'transport_request_id': self.default_req.id,
        }
        vals.update(kw)
        return self.env['pickup.plan'].create(vals)

    # ---- test_01: container 货型 — container_line_ids 可编辑 ----
    def test_01_cargo_type_container(self):
        plan = self._mk_plan(cargo_type='container')
        self.assertEqual(plan.cargo_type, 'container')
        # 创建集装箱明细行
        line = self.env['pickup.plan.container.line'].create({
            'plan_id': plan.id,
            'container_number': 'CONT-001',
            'container_type': '40HQ',
        })
        self.assertEqual(plan.container_line_ids[0].container_number, 'CONT-001')

    # ---- test_02: pallet 货型 — pallet/weight/volume 字段可录入 ----
    def test_02_cargo_type_pallet(self):
        plan = self._mk_plan(
            cargo_type='pallet', pallet_count=10,
            package_count=20, cargo_weight=500.0, cargo_volume=10.0,
        )
        self.assertEqual(plan.cargo_type, 'pallet')
        self.assertEqual(plan.pallet_count, 10)
        self.assertEqual(plan.cargo_weight, 500.0)

    # ---- test_03: warehouse → warehouse_id 必填 ----
    def test_03_dest_warehouse(self):
        with self.assertRaises(UserError):
            self._mk_plan(destination_type='warehouse', warehouse_id=False)

    # ---- test_04: warehouse_transfer — 双仓库必填 ----
    def test_04_dest_transfer(self):
        # source_warehouse_id 缺失 → UserError
        with self.assertRaises(UserError):
            self._mk_plan(
                destination_type='warehouse_transfer',
                source_warehouse_id=False,
            )
        # 双仓库均设置 → 正常
        plan = self._mk_plan(
            destination_type='warehouse_transfer',
            source_warehouse_id=self.wh2.id,
        )
        self.assertEqual(plan.source_warehouse_id, self.wh2)

    # ---- test_05: customer → partner_id 必填 ----
    def test_05_dest_customer(self):
        with self.assertRaises(UserError):
            self._mk_plan(destination_type='customer', partner_id=False)

    # ---- test_06: self_pickup → partner_id 必填 ----
    def test_06_dest_self_pickup(self):
        with self.assertRaises(UserError):
            self._mk_plan(destination_type='self_pickup', partner_id=False)

    # ---- test_07: Sprint50 state 状态机 + 下游订单派生 ----
    def test_07_lifecycle_by_downstream(self):
        plan = self._mk_plan()
        self.assertTrue(hasattr(plan, 'state'))
        self.assertEqual(plan.state, 'draft')
        plan.action_schedule()
        self.assertEqual(plan.state, 'scheduled')
        plan.scheduled_date = '2026-08-01 08:00:00'
        self.assertTrue(plan.scheduled_date)
        transport_type = self.env['tlmp.transport.type'].search([], limit=1)
        order = self.env['tlmp.transport.order'].create({
            'carrier_id': self.carrier.id,
            'partner_id': self.carrier.id,
            'transport_type_id': transport_type.id,
            'fleet_operation_mode': 'subcontracted',
            'pickup_plan_id': plan.id,
        })
        plan.transport_order_id = order.id
        self.assertTrue(plan.transport_order_id)

    # ---- test_08: IFFM 来源 — iff_requirement_ref 引用 ----
    def test_08_iff_source_reference(self):
        """IFFM 引用字段存在性校验（引用值验证需 wd_iffm 模块）"""
        plan = self._mk_plan()
        self.assertTrue(hasattr(plan, 'iff_requirement_ref'))
        if self.iff_req:
            ref = f'import.pickup.requirement,{self.iff_req.id}'
            plan.write({'iff_requirement_ref': ref})
            self.assertEqual(plan.iff_requirement_ref, ref)
        else:
            self.assertFalse(plan.iff_requirement_ref)
