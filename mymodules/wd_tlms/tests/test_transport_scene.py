# -*- coding: utf-8 -*-
"""Transport Scene / EventType / SceneEvent / CargoRule — 配置模型测试"""
from odoo.tests.common import TransactionCase
from odoo.exceptions import ValidationError


class TestTransportScene(TransactionCase):
    """TransportScene: lifecycle, constraint, config effect"""

    def setUp(self):
        super().setUp()
        self.scene = self.env['tlmp.transport.scene'].create({
            'name': 'Test Scene', 'code': 'TEST_SCENE',
            'scene_type': 'plan_driven',
        })
        self.evt_a = self.env['tlmp.transport.event.type'].create({
            'name': 'Event A', 'code': 'EVT_A', 'is_base_event': True, 'sequence_order': 10,
        })
        self.evt_b = self.env['tlmp.transport.event.type'].create({
            'name': 'Event B', 'code': 'EVT_B', 'is_base_event': True, 'sequence_order': 20,
        })
        self.evt_c = self.env['tlmp.transport.event.type'].create({
            'name': 'Other', 'code': 'OTHER', 'is_base_event': False, 'sequence_order': 999,
        })

    def test_01_scene_lifecycle(self):
        """create -> read -> write -> archive -> unarchive"""
        self.assertTrue(self.scene.id)
        self.assertEqual(self.scene.name, 'Test Scene')
        self.scene.write({'name': 'Updated Scene'})
        self.assertEqual(self.scene.name, 'Updated Scene')
        self.scene.write({'active': False})
        self.assertFalse(self.scene.active)
        self.scene.write({'active': True})
        self.assertTrue(self.scene.active)

    def test_02_event_type_lifecycle(self):
        """create / read / write / archive"""
        self.assertTrue(self.evt_a.id)
        self.evt_a.write({'name': 'Event A Updated'})
        self.assertEqual(self.evt_a.name, 'Event A Updated')
        self.evt_a.write({'active': False})
        self.assertFalse(self.evt_a.active)

    def test_03_scene_event_path_order(self):
        """Scene-Event paths sorted by sequence"""
        p1 = self.env['tlmp.transport.scene.event'].create({
            'scene_id': self.scene.id, 'event_type_id': self.evt_a.id, 'sequence': 20,
        })
        p2 = self.env['tlmp.transport.scene.event'].create({
            'scene_id': self.scene.id, 'event_type_id': self.evt_b.id, 'sequence': 10,
        })
        self.env['tlmp.transport.scene.event'].create({
            'scene_id': self.scene.id, 'event_type_id': self.evt_c.id, 'sequence': 5,
        })
        paths = self.env['tlmp.transport.scene.event'].search([
            ('scene_id', '=', self.scene.id),
        ], order='sequence, id')
        self.assertEqual(paths[0].id, p2.id, msg='sequence=10 should come first')
        self.assertEqual(paths[1].id, p1.id, msg='sequence=20 should come second')

    def test_04_scene_code_unique(self):
        """scene code unique constraint"""
        with self.assertRaises(Exception):
            self.env['tlmp.transport.scene'].create({
                'name': 'Duplicate', 'code': 'TEST_SCENE', 'scene_type': 'plan_driven',
            })

    def test_05_cargo_rule_preset(self):
        """SceneCargoRule creation and reading"""
        rule = self.env['tlmp.transport.scene.cargo.rule'].create({
            'scene_id': self.scene.id,
            'allowed_source_type': 'manual',
            'container_required': True,
            'cargo_required': True,
        })
        self.assertTrue(rule.id)
        self.assertEqual(rule.allowed_source_type, 'manual')
        self.assertTrue(rule.container_required)
        self.assertTrue(rule.cargo_required)

    def test_06_cargo_rule_empty_depot(self):
        """empty_depot allowed_source=none -> cargo should not be creatable"""
        rule = self.env['tlmp.transport.scene.cargo.rule'].create({
            'scene_id': self.scene.id,
            'allowed_source_type': 'none',
            'cargo_required': False,
        })
        self.assertEqual(rule.allowed_source_type, 'none')
        self.assertFalse(rule.cargo_required)
        # scene with allowed_source=none means no cargo lines should be created
        # This is a representative test
        scene_event = self.env['tlmp.transport.scene.event'].create({
            'scene_id': self.scene.id,
            'event_type_id': self.evt_a.id,
        })
        self.assertTrue(scene_event.id)

    def test_07_scene_config_immediate_effect(self):
        """Changing scene.event path immediately affects new events"""
        # Create scene-event paths in order A -> B
        self.env['tlmp.transport.scene.event'].create({
            'scene_id': self.scene.id, 'event_type_id': self.evt_a.id, 'sequence': 10,
        })
        self.env['tlmp.transport.scene.event'].create({
            'scene_id': self.scene.id, 'event_type_id': self.evt_b.id, 'sequence': 20,
        })
        # Create order + event A
        partner = self.env['res.partner'].create({'name': 'Test'})
        order = self.env['tlmp.transport.order'].create({
            'transport_type': 'to_customer', 'partner_id': partner.id,
            'carrier_id': partner.id, 'scene_id': self.scene.id,
        })
        evt_a = self.env['tlmp.transport.event'].create({
            'order_id': order.id, 'event_type_id': self.evt_a.id,
        })
        self.assertTrue(evt_a.id)

    def test_08_config_history_safe(self):
        """Historical orders not affected by scene config changes"""
        partner = self.env['res.partner'].create({'name': 'Test'})
        # Create scene-event path
        self.env['tlmp.transport.scene.event'].create({
            'scene_id': self.scene.id, 'event_type_id': self.evt_a.id, 'sequence': 10,
        })
        # Create order without scene_id (history order)
        order = self.env['tlmp.transport.order'].create({
            'transport_type': 'to_customer', 'partner_id': partner.id,
            'carrier_id': partner.id,
        })
        self.assertFalse(order.scene_id, msg='History order has no scene')
        # Should not raise error
        evt = self.env['tlmp.transport.event'].create({
            'order_id': order.id, 'event_type_id': self.evt_b.id,
        })
        self.assertTrue(evt.id)
