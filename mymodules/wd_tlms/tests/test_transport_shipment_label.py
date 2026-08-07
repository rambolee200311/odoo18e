# -*- coding: utf-8 -*-
"""Sprint25 — Shipment Label tests."""
from odoo.tests.common import TransactionCase
from odoo.exceptions import UserError


class TestShipmentLabel(TransactionCase):
    """Shipment Label CRUD + state machine"""

    def setUp(self):
        super().setUp()
        self.partner = self.env['res.partner'].create({'name': 'Test'})
        self.order = self.env['tlmp.transport.order'].create({
            'transport_type_id': self.env['tlmp.transport.type']._get_by_code('parcel').id,
            'partner_id': self.partner.id,
            'carrier_id': self.partner.id,
        })
        self.Label = self.env['tlmp.transport.shipment.label']

    def test_create_label(self):
        label = self.Label.create({'order_id': self.order.id})
        self.assertTrue(label)
        self.assertEqual(label.state, 'draft')
        self.assertTrue(label.name)
        self.assertIn('LBL/', label.name)

    def test_state_draft_to_generated(self):
        label = self.Label.create({'order_id': self.order.id})
        label.action_generate()
        self.assertEqual(label.state, 'generated')

    def test_state_draft_to_cancelled(self):
        label = self.Label.create({'order_id': self.order.id})
        label.action_cancel()
        self.assertEqual(label.state, 'cancelled')

    def test_state_generated_to_printed(self):
        label = self.Label.create({'order_id': self.order.id})
        label.action_generate()
        result = label.action_print()
        self.assertEqual(label.state, 'printed')
        self.assertIn('act_url', result.get('type', ''))

    def test_cancel_printed_blocked(self):
        label = self.Label.create({'order_id': self.order.id})
        label.action_generate()
        label.action_print()
        with self.assertRaises(UserError):
            label.action_cancel()

    def test_cancel_already_cancelled_blocked(self):
        label = self.Label.create({'order_id': self.order.id})
        label.action_cancel()
        with self.assertRaises(UserError):
            label.action_cancel()

    def test_generate_already_generated_blocked(self):
        label = self.Label.create({'order_id': self.order.id})
        label.action_generate()
        with self.assertRaises(UserError):
            label.action_generate()

    def test_print_without_generate_blocked(self):
        label = self.Label.create({'order_id': self.order.id})
        with self.assertRaises(UserError):
            label.action_print()

    def test_batch_print(self):
        l1 = self.Label.create({'order_id': self.order.id})
        l2 = self.Label.create({'order_id': self.order.id})
        l3 = self.Label.create({'order_id': self.order.id})
        l1.action_generate()
        l2.action_generate()
        batch = l1 + l2 + l3
        result = batch.action_print_batch()
        l1_invalid = self.assertRaises(UserError, l3.action_generate)
        self.assertEqual(l1.state, 'printed')
        self.assertEqual(l2.state, 'printed')
        self.assertEqual(l3.state, 'draft')
        self.assertIn('act_url', result.get('type', ''))

    def test_carrier_service_association(self):
        cs = self.env['tlmp.carrier.service'].create({
            'code': 'test_parcel',
            'name': 'Test Parcel',
            'service_type': 'parcel',
        })
        label = self.Label.create({
            'order_id': self.order.id,
            'carrier_service_id': cs.id,
        })
        self.assertEqual(label.carrier_service_id.id, cs.id)
        self.assertEqual(label.carrier_service_id.code, 'test_parcel')

    def test_multiple_labels_per_order(self):
        l1 = self.Label.create({'order_id': self.order.id})
        l2 = self.Label.create({'order_id': self.order.id})
        l3 = self.Label.create({'order_id': self.order.id})
        self.assertEqual(len(self.order.shipment_label_ids), 3)
        self.assertIn(l1, self.order.shipment_label_ids)
        self.assertIn(l2, self.order.shipment_label_ids)
        self.assertIn(l3, self.order.shipment_label_ids)

    def test_sequence_numbering(self):
        l1 = self.Label.create({'order_id': self.order.id, 'sequence': 10})
        l2 = self.Label.create({'order_id': self.order.id, 'sequence': 20})
        self.assertEqual(l1.sequence, 10)
        self.assertEqual(l2.sequence, 20)
        self.assertEqual(l2.name > l1.name, True)
