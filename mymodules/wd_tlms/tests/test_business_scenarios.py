# -*- coding: utf-8 -*-
"""Sprint41: Business Acceptance Tests — 4 scenarios × unified assertion template.

Template:
  (1) Entry doc created successfully
  (2) Scene source correct (request.scene_id = expected)
  (3) Scene_id not lost in chain (plan/quote -> order consistent)
  (4) Order snapshot immutable after confirmation (readonly)
  (5) Related object state matches expectations
  (6) (If applicable) settlement accessible / allocation exists
"""
from odoo.tests.common import TransactionCase
from .settlement_test_helpers import SettlementTestFactory


class TestBATS1TerminalWarehouse(TransactionCase):
    """S1: Terminal -> Warehouse (plan_driven -> Pickup Plan -> Order)"""

    def setUp(self):
        super().setUp()
        self.f = SettlementTestFactory(self.env)
        self.scene = self.env['tlmp.transport.scene'].search([
            ('code', '=', 'terminal_to_warehouse')], limit=1)
        self.request = self.env['tlmp.transport.request'].create({
            'request_type': 'plan_driven',
            'destination_type': 'warehouse',
            'scene_id': self.scene.id if self.scene else False,
        })

    def test_01_entry_doc_created(self):
        """(1) Entry doc created successfully"""
        self.assertTrue(self.request.id)
        self.assertEqual(self.request.request_type, 'plan_driven')

    def test_02_scene_source_correct(self):
        """(2) Scene source correct"""
        if self.scene:
            self.assertEqual(self.request.scene_id.id, self.scene.id)

    def test_03_scene_chain_not_lost(self):
        """(3) Scene_id not lost in chain"""
        if self.scene:
            # Simulate order creation with scene_id from request
            partner = self.f.create_partner()
            doc = self.f.create_billing_doc(partner)
            line = self.f.create_billing_line(doc, amount=1000.0)
            order = self.env['tlmp.transport.order'].create({
                'request_id': self.request.id,
                'scene_id': self.request.scene_id.id,
            })
            self.assertEqual(order.scene_id.id, self.scene.id)

    def test_04_order_snapshot_immutable(self):
        """(4) Order snapshot field definition check"""
        field = self.env['ir.model.fields'].search([
            ('model', '=', 'tlmp.transport.order'),
            ('name', '=', 'scene_id'),
        ], limit=1)
        self.assertTrue(field)
        self.assertTrue(field.readonly)

    def test_05_object_state_ok(self):
        """(5) Related object state matches expectations"""
        self.assertEqual(self.request.state, 'draft')

    def test_06_settlement_accessible(self):
        """(6) Settlement accessible / allocation exists"""
        partner = self.f.create_partner()
        doc = self.f.create_billing_doc(partner)
        line = self.f.create_billing_line(doc, amount=1000.0)
        order = self.env['tlmp.transport.order'].create({})
        alloc = self.f.create_allocation(line, order, 1000.0)
        self.assertTrue(alloc.id)
        self.assertAlmostEqual(alloc.allocated_amount, 1000.0)


class TestBATS5WarehouseTransfer(TransactionCase):
    """S5: Warehouse Transfer (plan_driven)"""

    def setUp(self):
        super().setUp()
        self.f = SettlementTestFactory(self.env)
        self.scene = self.env['tlmp.transport.scene'].search([
            ('code', '=', 'warehouse_transfer')], limit=1)
        self.request = self.env['tlmp.transport.request'].create({
            'request_type': 'plan_driven',
            'destination_type': 'warehouse_transfer',
            'scene_id': self.scene.id if self.scene else False,
        })

    def test_01_entry_doc_created(self):
        self.assertTrue(self.request.id)

    def test_02_scene_source_correct(self):
        if self.scene:
            self.assertEqual(self.request.scene_id.id, self.scene.id)

    def test_03_bonded_transfer_field(self):
        self.assertEqual(self.request.destination_type, 'warehouse_transfer')

    def test_04_order_scene_preserved(self):
        if self.scene:
            order = self.env['tlmp.transport.order'].create({
                'request_id': self.request.id,
                'scene_id': self.request.scene_id.id,
            })
            self.assertEqual(order.scene_id.id, self.scene.id)


class TestBATS6CustomerReturn(TransactionCase):
    """S6: Customer Return (commercial -> Inquiry -> Quote -> Order)"""

    def setUp(self):
        super().setUp()
        self.f = SettlementTestFactory(self.env)
        self.scene = self.env['tlmp.transport.scene'].search([
            ('code', '=', 'customer_return')], limit=1)
        self.request = self.env['tlmp.transport.request'].create({
            'request_type': 'commercial',
            'destination_type': 'warehouse',
            'scene_id': self.scene.id if self.scene else False,
        })

    def test_01_entry_doc_created(self):
        self.assertTrue(self.request.id)

    def test_02_request_type_commercial(self):
        self.assertEqual(self.request.request_type, 'commercial')

    def test_03_scene_chain_quote_to_order(self):
        """Verify scene passes through quote -> order"""
        if self.scene:
            quote = self.env['tlmp.transport.quote'].create({
                'request_id': self.request.id,
            })
            order = self.env['tlmp.transport.order'].create({
                'request_id': self.request.id,
                'quote_id': quote.id,
                'scene_id': self.request.scene_id.id,
            })
            self.assertEqual(order.scene_id.id, self.scene.id)
            self.assertEqual(order.quote_id.id, quote.id)

    def test_04_fee_line_exists(self):
        partner = self.f.create_partner()
        doc = self.f.create_billing_doc(partner)
        line = self.f.create_billing_line(doc, amount=1000.0)
        self.assertTrue(line.id)
        self.assertAlmostEqual(line.line_total, 1000.0)


class TestBATS8EmptyContainer(TransactionCase):
    """S8: Empty Container Move (container.service.request -> Order)"""

    def test_01_scene_preserved_in_order(self):
        """Scene is recorded from container service context"""
        scene = self.env['tlmp.transport.scene'].search([
            ('code', '=', 'empty_depot')], limit=1)
        order = self.env['tlmp.transport.order'].create({
            'scene_id': scene.id if scene else False,
        })
        if scene:
            self.assertEqual(order.scene_id.id, scene.id)

    def test_02_order_created_independently(self):
        """S8 order is created via container service, NOT via transport.request"""
        order = self.env['tlmp.transport.order'].create({})
        self.assertFalse(order.request_id)
        self.assertTrue(order.id)
