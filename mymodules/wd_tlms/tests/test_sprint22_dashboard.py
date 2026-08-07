# -*- coding: utf-8 -*-
"""Sprint22 — Dashboard Service + Cargo Rule + Report tests"""
from odoo.tests.common import TransactionCase


class TestDashboard(TransactionCase):
    """Dashboard Service + cards + actions"""

    def setUp(self):
        super().setUp()
        self.partner = self.env['res.partner'].create({'name': 'Test'})
        self.order = self.env['tlmp.transport.order'].create({
            'transport_type': 'to_customer', 'partner_id': self.partner.id,
            'carrier_id': self.partner.id,
        })
        self.svc = self.env['tlmp.transport.dashboard.service']

    def test_dashboard_service_no_table(self):
        self.assertEqual(self.svc._auto, False, msg='AbstractModel has no DB table')

    def test_event_timeout_card(self):
        result = self.svc.get_event_timeout_summary()
        self.assertIn('count', result)
        self.assertIn('records', result)

    def test_t1_overdue_card(self):
        result = self.svc.get_t1_overdue_summary()
        self.assertIn('count', result)
        self.assertIn('records', result)

    def test_exception_timeout_card(self):
        result = self.svc.get_exception_overdue_summary()
        self.assertIn('count', result)
        self.assertIn('records', result)


class TestCargoRule(TransactionCase):
    """Cargo Rule config + effect"""

    def setUp(self):
        super().setUp()
        self.partner = self.env['res.partner'].create({'name': 'Test'})
        self.scene = self.env['tlmp.transport.scene'].create({
            'name': 'Test Scene', 'code': 'TST', 'scene_type': 'plan_driven',
        })

    def test_cargo_rule_create(self):
        rule = self.env['tlmp.transport.scene.cargo.rule'].create({
            'scene_id': self.scene.id, 'allowed_source_type': 'manual',
            'container_required': True, 'cargo_required': True,
            'priority': 10,
        })
        self.assertTrue(rule.id)
        self.assertEqual(rule.priority, 10)

    def test_rule_changes_new_order(self):
        rule = self.env['tlmp.transport.scene.cargo.rule'].create({
            'scene_id': self.scene.id, 'allowed_source_type': 'none',
            'cargo_required': False, 'priority': 10,
        })
        self.assertEqual(rule.allowed_source_type, 'none')

    def test_old_order_not_affected(self):
        self.env['tlmp.transport.scene.cargo.rule'].create({
            'scene_id': self.scene.id, 'allowed_source_type': 'manual',
            'container_required': True, 'cargo_required': True,
            'priority': 10,
        })
        # Old order without scene_id should be unaffected
        order = self.env['tlmp.transport.order'].create({
            'transport_type': 'to_customer', 'partner_id': self.partner.id,
            'carrier_id': self.partner.id,
        })
        self.assertFalse(order.scene_id)
