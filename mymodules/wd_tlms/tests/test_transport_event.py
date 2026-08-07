# -*- coding: utf-8 -*-
"""Transport Event / Exception / ExtraCharge — 状态流转 + 约束测试"""
from odoo.tests.common import TransactionCase, TransactionCase
from odoo.exceptions import UserError, ValidationError


class TestTransportEvent(TransactionCase):
    """TransportEvent: state machine, sequence, POD, unlink"""

    def setUp(self):
        super().setUp()
        self.partner = self.env['res.partner'].create({'name': 'Test'})
        self.scene = self.env['tlmp.transport.scene'].create({
            'name': 'Event Test Scene', 'code': 'EVT_TEST',
            'scene_type': 'plan_driven',
        })
        self.evt_pickup = self.env['tlmp.transport.event.type'].create({
            'name': 'Pickup', 'code': 'PICKUP_ARRIVED',
            'is_base_event': True, 'sequence_order': 10,
        })
        self.evt_delivery = self.env['tlmp.transport.event.type'].create({
            'name': 'Delivery', 'code': 'DELIVERY_COMPLETED',
            'is_base_event': True, 'sequence_order': 20,
        })
        self.evt_other = self.env['tlmp.transport.event.type'].create({
            'name': 'Other', 'code': 'OTHER', 'is_base_event': False, 'sequence_order': 999,
        })
        self.order = self.env['tlmp.transport.order'].create({
            'transport_type': 'to_customer', 'partner_id': self.partner.id,
            'carrier_id': self.partner.id, 'scene_id': self.scene.id,
        })

    def test_10_event_create(self):
        evt = self.env['tlmp.transport.event'].create({
            'order_id': self.order.id, 'event_type_id': self.evt_pickup.id,
        })
        self.assertTrue(evt.id)
        self.assertEqual(evt.event_state, 'pending')

    def test_11_event_state_machine(self):
        evt = self.env['tlmp.transport.event'].create({
            'order_id': self.order.id, 'event_type_id': self.evt_pickup.id,
        })
        evt.action_set_in_progress()
        self.assertEqual(evt.event_state, 'in_progress')
        evt.action_complete()
        self.assertEqual(evt.event_state, 'completed')

    def test_12_event_skip_cancel_reason(self):
        evt = self.env['tlmp.transport.event'].create({
            'order_id': self.order.id, 'event_type_id': self.evt_pickup.id,
        })
        with self.assertRaises(ValidationError):
            evt.write({'event_state': 'skipped'})
        evt.write({'event_state': 'skipped', 'skip_cancel_reason': 'Not needed'})
        self.assertEqual(evt.event_state, 'skipped')

    def test_13_event_unlink_blocked(self):
        evt = self.env['tlmp.transport.event'].create({
            'order_id': self.order.id, 'event_type_id': self.evt_pickup.id,
        })
        with self.assertRaises(UserError):
            evt.unlink()

    def test_14_event_other_free(self):
        evt = self.env['tlmp.transport.event'].create({
            'order_id': self.order.id, 'event_type_id': self.evt_other.id,
        })
        self.assertTrue(evt.id)

    def test_15_event_pod_required(self):
        evt = self.env['tlmp.transport.event'].create({
            'order_id': self.order.id, 'event_type_id': self.evt_delivery.id,
        })
        evt.action_set_in_progress()
        with self.assertRaises(ValidationError):
            evt.write({'event_state': 'completed'})


class TestTransportException(TransactionCase):
    """TransportException: lifecycle, archive block, unlink"""

    def setUp(self):
        super().setUp()
        self.partner = self.env['res.partner'].create({'name': 'Test'})
        self.order = self.env['tlmp.transport.order'].create({
            'transport_type': 'to_customer', 'partner_id': self.partner.id,
            'carrier_id': self.partner.id,
        })

    def test_20_exception_create(self):
        exc = self.env['tlmp.transport.exception'].create({
            'order_id': self.order.id, 'exception_type': 'vehicle_breakdown',
            'description': 'Truck broke down',
        })
        self.assertTrue(exc.id)
        self.assertEqual(exc.exception_state, 'open')

    def test_21_exception_lifecycle(self):
        exc = self.env['tlmp.transport.exception'].create({
            'order_id': self.order.id, 'exception_type': 'traffic_delay',
            'description': 'Traffic jam',
        })
        exc.action_process()
        self.assertEqual(exc.exception_state, 'processing')
        exc.action_resolve()
        self.assertEqual(exc.exception_state, 'resolved')
        self.assertTrue(exc.resolved_time)
        exc.action_close()
        self.assertEqual(exc.exception_state, 'closed')
        self.assertTrue(exc.closed_time)

    def test_22_exception_unlink_blocked(self):
        exc = self.env['tlmp.transport.exception'].create({
            'order_id': self.order.id, 'exception_type': 'damage_shortage',
            'description': 'Damaged goods',
        })
        with self.assertRaises(UserError):
            exc.unlink()

    def test_23_order_archive_blocks_open_exceptions(self):
        exc = self.env['tlmp.transport.exception'].create({
            'order_id': self.order.id, 'exception_type': 'customs_hold',
            'description': 'Customs inspection',
        })
        with self.assertRaises(UserError):
            self.order.action_close()


class TestExtraCharge(TransactionCase):
    """ExtraCharge: CRUD, summary"""

    def setUp(self):
        super().setUp()
        self.partner = self.env['res.partner'].create({'name': 'Test'})
        self.order = self.env['tlmp.transport.order'].create({
            'transport_type': 'to_customer', 'partner_id': self.partner.id,
            'carrier_id': self.partner.id,
        })

    def test_25_charge_create(self):
        chg = self.env['tlmp.transport.extra.charge'].create({
            'order_id': self.order.id, 'charge_type': 'detention',
            'amount': 150.0, 'party_type': 'customer',
        })
        self.assertTrue(chg.id)
        self.assertEqual(chg.amount, 150.0)

    def test_26_charge_summary(self):
        self.env['tlmp.transport.extra.charge'].create({
            'order_id': self.order.id, 'charge_type': 'waiting',
            'amount': 100.0, 'party_type': 'carrier',
        })
        self.env['tlmp.transport.extra.charge'].create({
            'order_id': self.order.id, 'charge_type': 'customs_fee',
            'amount': 50.0, 'party_type': 'customer',
        })
        charges = self.env['tlmp.transport.extra.charge'].search([
            ('order_id', '=', self.order.id),
        ])
        total = sum(charges.mapped('amount'))
        self.assertEqual(total, 150.0)
