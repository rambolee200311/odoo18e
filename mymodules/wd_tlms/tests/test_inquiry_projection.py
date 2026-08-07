# -*- coding: utf-8 -*-
"""Sprint46: Inquiry related address projection tests"""
from odoo.tests.common import TransactionCase


class TestInquiryProjection(TransactionCase):
    def setUp(self):
        super().setUp()
        self.terminal = self.env['res.partner'].create({
            'name': 'Rotterdam Terminal', 'street': 'Boompijes 258',
            'zip': '3011XZ', 'city': 'Rotterdam',
        })
        self.customer = self.env['res.partner'].create({
            'name': 'Test Customer', 'street': 'Main St 1', 'city': 'Amsterdam',
        })
        self.scene_tc = self.env['tlmp.transport.scene'].search(
            [('code', '=', 'terminal_to_customer')], limit=1)
        self.req = self.env['tlmp.transport.request'].create({
            'request_type': 'commercial',
            'destination_type': 'customer',
            'cargo_type': 'container',
            'scene_id': self.scene_tc.id,
            'partner_id': self.customer.id,
            'terminal_id': self.terminal.id,
            'origin_street': self.terminal.street,
            'origin_city': self.terminal.city,
            'destination_street': 'Customer St 9',
            'destination_city': 'Amsterdam',
        })

    def _mk_inquiry(self):
        return self.env['tlmp.transport.inquiry'].create({
            'request_id': self.req.id,
            'partner_id': self.customer.id,
        })

    def test_related_projection_readonly(self):
        """Inquiry related 字段实时读取 Request 地址且为只读"""
        inq = self._mk_inquiry()
        self.assertEqual(inq.origin_street, self.terminal.street)
        self.assertEqual(inq.origin_city, self.terminal.city)
        self.assertEqual(inq.destination_street, 'Customer St 9')
        # related 字段应为只读
        self.assertTrue(inq._fields['origin_street'].readonly)
        self.assertTrue(inq._fields['destination_city'].readonly)

    def test_projection_syncs_after_request_change(self):
        """Request 地址变更后 Inquiry 投影同步（related 实时）"""
        inq = self._mk_inquiry()
        self.req.write({'origin_street': 'Updated Street 123'})
        self.assertEqual(inq.origin_street, 'Updated Street 123')

    def test_legacy_text_not_in_chain(self):
        """from_location_text / to_location_text 仅作兼容展示，不参与新链路"""
        inq = self._mk_inquiry()
        # 旧文本字段允许为空/自由填写，不自动从新地址投影
        inq.write({'from_location_text': 'Legacy From', 'to_location_text': 'Legacy To'})
        self.assertEqual(inq.from_location_text, 'Legacy From')
        self.assertEqual(inq.to_location_text, 'Legacy To')
        # 新地址字段仍来自 request 投影
        self.assertEqual(inq.origin_street, self.terminal.street)
