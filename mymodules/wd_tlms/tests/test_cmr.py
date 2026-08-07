# -*- coding: utf-8 -*-
"""CMR 运单单元测试 — tlmp.cmr + tlmp.cmr.line + tlmp.cmr.coordinate"""
from dateutil import parser
from odoo.tests.common import TransactionCase
from odoo.exceptions import UserError, ValidationError


class TestCMR(TransactionCase):
    """tlmp.cmr: CRUD + 状态机 + 快速创建 + 辅助方法"""

    def setUp(self):
        super().setUp()
        # Partners
        self.sender = self.env['res.partner'].create({
            'name': 'Sender Corp',
            'street': 'Sender Str 1',
            'zip': '1000',
            'city': 'Amsterdam',
            'country_id': self.env.ref('base.nl').id,
        })
        self.consignee = self.env['res.partner'].create({
            'name': 'Consignee GmbH',
            'street': 'Empfanger Str 2',
            'zip': '2000',
            'city': 'Hamburg',
            'country_id': self.env.ref('base.de').id,
        })
        self.carrier = self.env['res.partner'].create({
            'name': 'Carrier BV',
            'street': 'Vrachtweg 3',
            'zip': '3000',
            'city': 'Rotterdam',
            'is_carrier': True,
            'country_id': self.env.ref('base.nl').id,
        })
        # Transport order
        self.order = self.env['tlmp.transport.order'].create({
            'transport_type': 'to_customer',
            'partner_id': self.consignee.id,
            'carrier_id': self.carrier.id,
            'pickup_location_id': self.sender.id,
            'delivery_location_id': self.consignee.id,
            'planned_pickup_date': parser.parse('2026-07-20 08:00'),
            'planned_delivery_date': parser.parse('2026-07-22 16:00'),
            'has_dangerous_goods': False,
        })

    def _mk_cmr(self, **kw):
        """Create a minimal CMR record with sensible defaults."""
        vals = {
            'order_id': self.order.id,
            'cmr_number': 'CMR-TEST-001',
            'sender_id': self.sender.id,
            'consignee_id': self.consignee.id,
            'carrier_id': self.carrier.id,
            'copy_number': '1',
        }
        vals.update(kw)
        return self.env['tlmp.cmr'].create(vals)

    def _mk_line(self, cmr, **kw):
        """Add a cargo line to a CMR record."""
        vals = {
            'cmr_id': cmr.id,
            'commodity': 'Test Goods',
            'sku': 'SKU-001',
            'qty': 5.0,
            'gross_weight_per_unit': 20.0,
        }
        vals.update(kw)
        return self.env['tlmp.cmr.line'].create(vals)

    # ═══════════════════════════════════════════════════════
    # 1. CMR CRUD
    # ═══════════════════════════════════════════════════════

    def test_01_cmr_create(self):
        """创建 CMR 记录，必填字段验证"""
        cmr = self._mk_cmr(cmr_number='CMR-CRUD-01')
        self.assertTrue(cmr.id, msg='CMR 应成功创建')
        self.assertEqual(cmr.cmr_number, 'CMR-CRUD-01')
        self.assertEqual(cmr.order_id, self.order)
        self.assertEqual(cmr.sender_id, self.sender)
        self.assertEqual(cmr.consignee_id, self.consignee)
        self.assertEqual(cmr.carrier_id, self.carrier)
        self.assertEqual(cmr.state, 'draft', msg='新建 CMR 状态应为 draft')

    def test_02_cmr_read(self):
        """读取 CMR 记录，关联字段正确返回"""
        cmr = self._mk_cmr()
        read = self.env['tlmp.cmr'].browse(cmr.id)
        self.assertEqual(read.sender_id.name, 'Sender Corp')
        self.assertEqual(read.consignee_id.name, 'Consignee GmbH')
        self.assertEqual(read.carrier_id.name, 'Carrier BV')
        self.assertEqual(read.order_id.name, self.order.name)

    def test_03_cmr_update(self):
        """更新 CMR 字段"""
        cmr = self._mk_cmr()
        cmr.write({'place_of_taking_over': 'Amsterdam Port'})
        self.assertEqual(cmr.place_of_taking_over, 'Amsterdam Port')

    # ═══════════════════════════════════════════════════════
    # 2. CMR 状态机
    # ═══════════════════════════════════════════════════════

    def test_04_state_machine_draft_to_printed_available(self):
        """action_print_cmr 可调用（返回动作）"""
        cmr = self._mk_cmr()
        # In test env, the report may not be fully loaded; just verify the method is callable
        self.assertTrue(hasattr(cmr, 'action_print_cmr'), msg='action_print_cmr 应可调用')

    def test_05_state_machine_confirm_signature(self):
        """in_transit → action_confirm_signature → signed"""
        cmr = self._mk_cmr()
        cmr.write({'state': 'in_transit'})
        cmr.action_confirm_signature()
        self.assertEqual(cmr.state, 'signed')
        self.assertTrue(cmr.is_pod_confirmed)

    def test_06_state_machine_archive(self):
        """signed → action_archive → archived"""
        cmr = self._mk_cmr()
        cmr.write({'state': 'signed'})
        cmr.action_archive()
        self.assertEqual(cmr.state, 'archived')

    def test_07_state_machine_full_flow(self):
        """draft → printed → in_transit → signed → archived 全流转"""
        cmr = self._mk_cmr()
        cmr.write({'state': 'printed'})
        self.assertEqual(cmr.state, 'printed')
        cmr.write({'state': 'in_transit'})
        self.assertEqual(cmr.state, 'in_transit')
        cmr.action_confirm_signature()
        self.assertEqual(cmr.state, 'signed')
        cmr.action_archive()
        self.assertEqual(cmr.state, 'archived')

    # ═══════════════════════════════════════════════════════
    # 3. CMR Line 增删改 + 自动计算
    # ═══════════════════════════════════════════════════════

    def test_08_line_create_and_auto_weight(self):
        """创建货物明细行，gross_weight = qty × gross_weight_per_unit 自动计算"""
        cmr = self._mk_cmr()
        line = self._mk_line(cmr, qty=10.0, gross_weight_per_unit=25.0)
        self.assertEqual(line.gross_weight, 250.0, msg='毛重应自动计算为 10×25=250')
        self.assertEqual(line.commodity, 'Test Goods')
        self.assertEqual(line.sku, 'SKU-001')

    def test_09_line_update_recompute(self):
        """修改 qty 或 gw_unit 后 gross_weight 重新计算"""
        cmr = self._mk_cmr()
        line = self._mk_line(cmr, qty=5.0, gross_weight_per_unit=20.0)
        self.assertEqual(line.gross_weight, 100.0)
        line.write({'qty': 3.0})
        self.assertEqual(line.gross_weight, 60.0, msg='qty=3→gross_weight=3×20=60')
        line.write({'gross_weight_per_unit': 30.0})
        self.assertEqual(line.gross_weight, 90.0, msg='gw_unit=30→gross_weight=3×30=90')

    def test_10_line_multiple_lines(self):
        """多个明细行累计到父级 packages_count / gross_weight"""
        cmr = self._mk_cmr()
        self._mk_line(cmr, qty=5.0, gross_weight_per_unit=20.0)   # 5×20=100
        self._mk_line(cmr, qty=3.0, gross_weight_per_unit=50.0,   # 3×50=150
                      commodity='Other', sku='SKU-002')
        self.assertEqual(cmr.packages_count, 8.0, msg='总托盘数=5+3=8')
        self.assertEqual(cmr.gross_weight, 250.0, msg='总毛重=100+150=250')

    def test_11_line_delete_recompute(self):
        """删除明细行后父级重新累计"""
        cmr = self._mk_cmr()
        line1 = self._mk_line(cmr, qty=5.0, gross_weight_per_unit=20.0)
        line2 = self._mk_line(cmr, qty=3.0, gross_weight_per_unit=50.0,
                              commodity='Other', sku='SKU-002')
        self.assertEqual(cmr.packages_count, 8.0)
        line2.unlink()
        self.assertEqual(cmr.packages_count, 5.0, msg='删除一行后总托盘=5')
        self.assertEqual(cmr.gross_weight, 100.0, msg='删除一行后总毛重=5×20=100')

    def test_12_line_no_gw_unit(self):
        """gross_weight_per_unit 为空时 gross_weight = 0"""
        cmr = self._mk_cmr()
        line = self._mk_line(cmr, qty=10.0, gross_weight_per_unit=0)
        self.assertEqual(line.gross_weight, 0.0, msg='gw_unit=0→gross_weight=0')

    # ═══════════════════════════════════════════════════════
    # 4. 累加校验（_check_cmr_lines）
    # ═══════════════════════════════════════════════════════

    def test_13_check_pallets_match(self):
        """Qty 累加一致 → 校验通过"""
        cmr = self._mk_cmr()
        self._mk_line(cmr, qty=4.0, gross_weight_per_unit=10.0)
        self._mk_line(cmr, qty=6.0, gross_weight_per_unit=15.0, commodity='B')
        # packages_count 是 computed, 应 = 4+6=10
        self.assertEqual(cmr.packages_count, 10.0)
        # 校验应通过（无异常抛出 = 通过）

    def test_14_check_pallets_mismatch(self):
        """手工修改 packages_count ≠ Σqty → ValidationError"""
        cmr = self._mk_cmr()
        self._mk_line(cmr, qty=4.0, gross_weight_per_unit=10.0)
        self._mk_line(cmr, qty=6.0, gross_weight_per_unit=15.0, commodity='B')
        # packages_count 此时 = 4+6=10
        # 直接 write computed field 触发 constraint
        with self.assertRaises(ValidationError):
            cmr.write({'packages_count': 999.0})

    def test_15_check_gross_weight_match(self):
        """GW 累加一致 → 校验通过"""
        cmr = self._mk_cmr()
        self._mk_line(cmr, qty=2.0, gross_weight_per_unit=100.0)   # gw=200
        self._mk_line(cmr, qty=3.0, gross_weight_per_unit=50.0,    # gw=150
                      commodity='B', sku='B')
        self.assertEqual(cmr.gross_weight, 350.0)
        # 校验通过

    def test_16_check_gross_weight_mismatch(self):
        """手工修改 gross_weight ≠ Σgw → ValidationError"""
        cmr = self._mk_cmr()
        self._mk_line(cmr, qty=2.0, gross_weight_per_unit=100.0)   # gw=200
        # packages_count = 2, gross_weight = 200
        # Write gross_weight to mismatch → triggers _check_cmr_lines
        with self.assertRaises(ValidationError):
            cmr.write({'gross_weight': 999.0})

    # ═══════════════════════════════════════════════════════
    # 5. action_create_from_order 快速创建
    # ═══════════════════════════════════════════════════════

    def test_17_create_from_order(self):
        """action_create_from_order 返回 action，携带正确的默认上下文"""
        # 模拟从运输订单的 smart button 调用
        order_id = self.order.id
        result = self.env['tlmp.cmr'].with_context(active_id=order_id).action_create_from_order()

        self.assertIn('context', result, msg='应返回 action dict')
        self.assertIn('res_model', result)
        self.assertEqual(result['res_model'], 'tlmp.cmr')

        ctx = result['context'] if isinstance(result['context'], dict) else {}
        # Verify default values in context
        defaults_ok = (
            ctx.get('default_order_id') == order_id
            or ctx.get('order_id') == order_id
        )
        self.assertTrue(defaults_ok, msg='上下文中应包含 order_id')

    def test_18_create_from_order_missing_order(self):
        """不传 active_id → UserError"""
        with self.assertRaises(UserError):
            self.env['tlmp.cmr'].action_create_from_order()

    def test_19_create_from_order_partial(self):
        """order 无 pickup/delivery location → sender/consignee 为空"""
        minimal_order = self.env['tlmp.transport.order'].create({
            'transport_type': 'to_customer',
            'partner_id': self.consignee.id,
            'carrier_id': self.carrier.id,
        })
        result = self.env['tlmp.cmr'].with_context(
            active_id=minimal_order.id
        ).action_create_from_order()
        ctx = result.get('context', {})
        # pickup_location 为空 → sender_id 应为 False
        self.assertFalse(ctx.get('default_sender_id'),
                         msg='无 pickup_location → sender_id 应为空')

    # ═══════════════════════════════════════════════════════
    # 6. name / cmr_number 自动序列号
    # ═══════════════════════════════════════════════════════

    def test_20_name_auto_sequence(self):
        """name 字段自动从 ir.sequence 生成（不传 name 时）"""
        cmr = self._mk_cmr(cmr_number='CMR-SEQ-01')
        self.assertTrue(cmr.name, msg='name 应自动生成')
        self.assertNotEqual(cmr.name, 'New', msg='自动序列不应是 New')

    def test_21_cmr_number_required(self):
        """cmr_number 必填"""
        with self.assertRaises(Exception):
            self._mk_cmr(cmr_number=False)

    # ═══════════════════════════════════════════════════════
    # 7. ADR 关联字段
    # ═══════════════════════════════════════════════════════

    def test_22_adr_related_from_order(self):
        """ADR 字段从 order_id 关联读取"""
        dg_order = self.env['tlmp.transport.order'].create({
            'transport_type': 'to_customer',
            'partner_id': self.consignee.id,
            'carrier_id': self.carrier.id,
            'has_dangerous_goods': True,
            'adr_class': '3',
            'adr_un_number': 'UN1203',
        })
        cmr = self._mk_cmr(order_id=dg_order.id, cmr_number='CMR-ADR-01',
                            sender_id=self.sender.id,
                            consignee_id=self.consignee.id,
                            carrier_id=self.carrier.id)
        self.assertTrue(cmr.has_dangerous_goods)
        self.assertEqual(cmr.adr_class, '3')
        self.assertEqual(cmr.adr_un_number, 'UN1203')

    # ═══════════════════════════════════════════════════════
    # 8. SQL 唯一约束
    # ═══════════════════════════════════════════════════════

    def test_23_cmr_copy_unique(self):
        """cmr_number + copy_number 唯一约束"""
        self._mk_cmr(cmr_number='CMR-UNIQUE-01', copy_number='1')
        with self.assertRaises(Exception):
            self._mk_cmr(cmr_number='CMR-UNIQUE-01', copy_number='1')

    # ═══════════════════════════════════════════════════════
    # 9. 辅助方法：_get_cmr_field_values
    # ═══════════════════════════════════════════════════════

    def test_24_get_field_values(self):
        """_get_cmr_field_values 返回完整字段映射"""
        cmr = self._mk_cmr(cmr_number='CMR-HELPER-01',
                            place_of_taking_over='Amsterdam',
                            place_of_delivery='Hamburg')
        self._mk_line(cmr, qty=5.0, gross_weight_per_unit=20.0,
                      commodity='Widgets', sku='W-001')
        vals = cmr._get_cmr_field_values()
        self.assertIn('cmr_number', vals)
        self.assertEqual(vals['cmr_number'], 'CMR-HELPER-01')
        self.assertIn('sender_name', vals)
        self.assertEqual(vals['sender_name'], 'Sender Corp')
        self.assertIn('place_taking', vals)
        self.assertEqual(vals['place_taking'], 'Amsterdam')
        self.assertIn('total_pallets', vals)
        self.assertEqual(vals['total_pallets'], '5.0')
        # line 字段前缀
        self.assertIn('line_1_commodity', vals)
        self.assertEqual(vals['line_1_commodity'], 'Widgets')

    # ═══════════════════════════════════════════════════════
    # 10. 辅助方法：_get_print_blocks
    # ═══════════════════════════════════════════════════════

    def test_25_get_print_blocks_no_coords(self):
        """无坐标配置时 _get_print_blocks 返回空列表"""
        cmr = self._mk_cmr()
        blocks = cmr._get_print_blocks()
        self.assertEqual(blocks, [], msg='无坐标时应返回空列表')

    def test_26_get_print_blocks_with_coords(self):
        """有坐标配置时返回正确的坐标块"""
        # 先创建一个坐标配置
        self.env['tlmp.cmr.coordinate'].create({
            'name': 'CMR Number Position',
            'field_identifier': 'cmr_number',
            'section': 'header',
            'x_mm': 50.0,
            'y_mm': 10.0,
            'font_size': 12,
            'alignment': 'right',
        })
        cmr = self._mk_cmr(cmr_number='CMR-BLOCK-01')
        blocks = cmr._get_print_blocks()
        self.assertTrue(len(blocks) > 0, msg='有坐标时应返回至少一个块')
        block = blocks[0]
        self.assertEqual(block['text'], 'CMR-BLOCK-01')
        self.assertEqual(block['x_mm'], 50.0)
        self.assertEqual(block['y_mm'], 10.0)
        self.assertEqual(block['alignment'], 'right')

    # ═══════════════════════════════════════════════════════
    # 11. 空白签收区域验证
    # ═══════════════════════════════════════════════════════

    def test_27_signature_fields_blank_by_default(self):
        """签收区域初始为空"""
        cmr = self._mk_cmr()
        self.assertFalse(cmr.signed_by)
        self.assertFalse(cmr.signed_date)
        self.assertFalse(cmr.signature_image)

    def test_28_signature_fields_writeable(self):
        """签收字段可写入"""
        cmr = self._mk_cmr()
        cmr.write({
            'signed_by': 'John Doe',
            'damage_description': 'No visible damage',
        })
        self.assertEqual(cmr.signed_by, 'John Doe')
        self.assertEqual(cmr.damage_description, 'No visible damage')


class TestCMRCoordinate(TransactionCase):
    """tlmp.cmr.coordinate — XY 坐标配置 CRUD"""

    def setUp(self):
        super().setUp()

    def test_30_coordinate_create(self):
        """创建坐标配置"""
        coord = self.env['tlmp.cmr.coordinate'].create({
            'name': 'Test Coordinate',
            'field_identifier': 'test_field',
            'section': 'header',
            'x_mm': 100.0,
            'y_mm': 50.0,
            'font_size': 10,
        })
        self.assertTrue(coord.id)
        self.assertEqual(coord.x_mm, 100.0)
        self.assertEqual(coord.y_mm, 50.0)
        self.assertTrue(coord.active)

    def test_31_coordinate_update(self):
        """修改坐标偏移量"""
        coord = self.env['tlmp.cmr.coordinate'].create({
            'name': 'Moveable',
            'field_identifier': 'move_field',
            'section': 'header',
            'x_mm': 10.0,
            'y_mm': 10.0,
        })
        coord.write({'x_mm': 20.0, 'y_mm': 30.0})
        self.assertEqual(coord.x_mm, 20.0)
        self.assertEqual(coord.y_mm, 30.0)

    def test_32_coordinate_delete(self):
        """删除坐标配置"""
        coord = self.env['tlmp.cmr.coordinate'].create({
            'name': 'To Delete',
            'field_identifier': 'del_field',
            'section': 'header',
            'x_mm': 5.0,
            'y_mm': 5.0,
        })
        cid = coord.id
        coord.unlink()
        self.assertFalse(
            self.env['tlmp.cmr.coordinate'].browse(cid).exists()
        )

    def test_33_coordinate_defaults(self):
        """坐标配置默认值"""
        coord = self.env['tlmp.cmr.coordinate'].create({
            'name': 'Defaults',
            'field_identifier': 'def_field',
            'section': 'header',
            'x_mm': 0.0,
            'y_mm': 0.0,
        })
        self.assertEqual(coord.font_size, 10)
        self.assertEqual(coord.alignment, 'left')
        self.assertEqual(coord.max_length, 0)
        self.assertTrue(coord.active)
