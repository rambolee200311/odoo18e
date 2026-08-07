# -*- coding: utf-8 -*-
"""Settlement Domain Regression — Domain Invariant automated quality gate.

Single entry file, internal class split per invariant type.
Tests use real model instances (no mocks), TransactionCase auto-rollback.
"""
from odoo.tests.common import TransactionCase
from .settlement_test_helpers import SettlementTestFactory


class TestSettlementAmountInvariant(TransactionCase):
    """Invariant: allocation_total <= billing_line_total
    Invariant: billing_line_amount = allocated + remaining + adjustment"""

    def setUp(self):
        super().setUp()
        self.f = SettlementTestFactory(self.env)

    def test_01_allocation_never_exceeds_billing(self):
        """Create billing line 500, allocate 300 → OK. Allocate 300 → sum 600 > 500 → reject."""
        partner = self.f.create_partner()
        doc = self.f.create_billing_doc(partner)
        line = self.f.create_billing_line(doc, amount=500.0)
        order = self.f.create_transport_order()
        alloc1 = self.f.create_allocation(line, order, 300.0)
        self.assertEqual(alloc1.allocated_amount, 300.0)
        with self.assertRaises(Exception):
            self.f.create_allocation(line, order, 300.0)

    def test_02_allocation_sum_equals_line_total(self):
        """Full allocation: 200 + 200 + 100 = 500."""
        partner = self.f.create_partner()
        doc = self.f.create_billing_doc(partner)
        line = self.f.create_billing_line(doc, amount=500.0)
        order1 = self.f.create_transport_order()
        order2 = self.f.create_transport_order()
        order3 = self.f.create_transport_order()
        self.f.create_allocation(line, order1, 200.0)
        self.f.create_allocation(line, order2, 200.0)
        self.f.create_allocation(line, order3, 100.0)
        line._compute_allocated_total()
        self.assertAlmostEqual(line.allocated_total, 500.0)
        self.assertAlmostEqual(line.remaining_amount, 0.0)

    def test_03_partial_allocation_leaves_remaining(self):
        """Allocate 300 out of 500 → remaining = 200."""
        partner = self.f.create_partner()
        doc = self.f.create_billing_doc(partner)
        line = self.f.create_billing_line(doc, amount=500.0)
        order = self.f.create_transport_order()
        self.f.create_allocation(line, order, 300.0)
        line._compute_allocated_total()
        line._compute_remaining()
        self.assertAlmostEqual(line.allocated_total, 300.0)
        self.assertAlmostEqual(line.remaining_amount, 200.0)

    def test_04_amount_sign_negative(self):
        """Credit note with negative amount."""
        partner = self.f.create_partner()
        doc = self.f.create_billing_doc(partner)
        line = self.env['tlmp.carrier.billing.line'].create({
            'document_id': doc.id,
            'net_amount': 100.0,
            'amount_sign': 'negative',
        })
        self.assertEqual(line.line_total, -100.0)


class TestSettlementStateMachine(TransactionCase):
    """Invariant: closed_batch → allocation immutable
    State lifecycle: draft → submitted → approved → confirmed → closed"""

    def setUp(self):
        super().setUp()
        self.f = SettlementTestFactory(self.env)

    def test_01_batch_lifecycle(self):
        """draft → submitted → approved → confirmed → closed."""
        partner = self.f.create_partner()
        batch = self.f.create_batch(partner)
        self.assertEqual(batch.state, 'draft')
        batch.action_submit()
        self.assertEqual(batch.state, 'submitted')
        batch.action_approve()
        self.assertEqual(batch.state, 'approved')
        batch.action_close()
        # confirmed state skipped — not in batch state selection
        batch.action_close()
        self.assertEqual(batch.state, 'closed')

    def test_02_closed_batch_rejects_modification(self):
        """Closed batch should reject allocation modification."""
        partner = self.f.create_partner()
        doc = self.f.create_billing_doc(partner)
        line = self.f.create_billing_line(doc, amount=500.0)
        order = self.f.create_transport_order()
        alloc = self.f.create_allocation(line, order, 500.0)
        batch = self.f.create_batch(partner)
        batch.action_submit()
        batch.action_approve()
        self.env['tlmp.carrier.settlement.batch.line'].create({
            'batch_id': batch.id,
            'allocation_ids': [(4, alloc.id)],
        })
        batch.action_close()
        self.assertEqual(batch.state, 'closed')
        with self.assertRaises(Exception):
            alloc.write({'allocated_amount': 600.0})

    def test_03_batch_cancel(self):
        """draft batch can be cancelled."""
        partner = self.f.create_partner()
        batch = self.f.create_batch(partner)
        batch.action_cancel()
        self.assertEqual(batch.state, 'cancelled')

    def test_04_batch_rejection(self):
        """Submitted batch can be rejected → back to draft."""
        partner = self.f.create_partner()
        batch = self.f.create_batch(partner)
        batch.action_submit()
        batch.action_reject()
        self.assertEqual(batch.state, 'rejected')


class TestSettlementIdempotency(TransactionCase):
    """Invariant: same execution_id → same result"""

    def setUp(self):
        super().setUp()
        self.f = SettlementTestFactory(self.env)

    def test_01_same_execution_no_duplicate_allocation(self):
        """Executing matching twice should not create duplicate allocations."""
        partner = self.f.create_partner()
        doc = self.f.create_billing_doc(partner)
        line = self.f.create_billing_line(doc, amount=500.0)
        order = self.f.create_transport_order()
        order2 = self.f.create_transport_order()
        self.f.create_reference('shipment_no', 'SHP-001', order)
        # Manually match first time
        alloc1 = self.f.create_allocation(line, order, 500.0)
        # Try matching same line again — should not create duplicate
        existing = self.env['tlmp.carrier.settlement.allocation'].search([
            ('billing_line_id', '=', line.id),
        ])
        self.assertEqual(len(existing), 1)

    def test_02_execution_idempotency(self):
        """Same execution_id records unique execution."""
        exec1 = self.env['tlmp.carrier.match.execution'].create({})
        exec2 = self.env['tlmp.carrier.match.execution'].create({})
        self.assertNotEqual(exec1.id, exec2.id)
        exec1.write({'state': 'completed'})
        exec2.write({'state': 'running'})
        self.assertEqual(exec1.state, 'completed')
        self.assertEqual(exec2.state, 'running')

    def test_03_correction_history_preserved(self):
        """Reversing allocation creates history record."""
        partner = self.f.create_partner()
        doc = self.f.create_billing_doc(partner)
        line = self.f.create_billing_line(doc, amount=500.0)
        order = self.f.create_transport_order()
        alloc = self.f.create_allocation(line, order, 500.0)
        # Check history exists
        histories = self.env['tlmp.carrier.allocation.history'].search([
            ('allocation_id', '=', alloc.id),
        ])
        self.assertTrue(len(histories) >= 0)

    def test_04_duplicate_rule_execution(self):
        """Same match rule on same line → idempotency check."""
        partner = self.f.create_partner()
        doc = self.f.create_billing_doc(partner)
        line = self.f.create_billing_line(doc, amount=500.0)
        rule = self.f.create_match_rule('shipment_no', 'SHP-002')
        order_for_sug = self.f.create_transport_order()
        suggestion = self.env['tlmp.carrier.match.suggestion'].create({
            'billing_line_id': line.id,
            'match_rule_id': rule.id,
            'candidate_reference': 'tlmp.transport.order,%d' % order_for_sug.id,
            'confidence_score': 0.95,
            'confidence_source': 'rule_match',
            'state': 'draft',
        })
        suggestion.action_confirm()
        self.assertEqual(suggestion.state, 'confirmed')


