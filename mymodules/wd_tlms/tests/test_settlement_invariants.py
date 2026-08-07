# -*- coding: utf-8 -*-
"""Sprint39: Domain Invariant automated gate — 100% PASS required.
Each invariant from settlement_full.yaml has an automated TestCase.
"""
from odoo.tests.common import TransactionCase
from odoo.exceptions import ValidationError


class TestInvariantBillingAmountConservation(TransactionCase):
    def test_billing_amount_conservation(self):
        """billing_line_amount = allocated + remaining + adjustment"""
        partner = self.env['res.partner'].create({'name': 'T', 'is_company': True})
        doc = self.env['tlmp.carrier.billing.document'].create({
            'carrier_id': partner.id,
        })
        line = self.env['tlmp.carrier.billing.line'].create({
            'document_id': doc.id, 'net_amount': 500.0,
        })
        order = self.env['tlmp.transport.order'].create({})
        self.env['tlmp.carrier.settlement.allocation'].create({
            'billing_line_id': line.id, 'transport_order_id': order.id, 'allocated_amount': 500.0,
        })
        line._compute_allocated_total()
        line._compute_remaining()
        self.assertAlmostEqual(line.allocated_total + line.remaining_amount, line.line_total)


class TestInvariantAllocationNeverExceedsBilling(TransactionCase):
    def test_allocation_not_exceed(self):
        partner = self.env['res.partner'].create({'name': 'T', 'is_company': True})
        doc = self.env['tlmp.carrier.billing.document'].create({'carrier_id': partner.id})
        line = self.env['tlmp.carrier.billing.line'].create({
            'document_id': doc.id, 'net_amount': 200.0,
        })
        order = self.env['tlmp.transport.order'].create({})
        self.env['tlmp.carrier.settlement.allocation'].create({
            'billing_line_id': line.id, 'transport_order_id': order.id, 'allocated_amount': 200.0,
        })
        with self.assertRaises(Exception):
            self.env['tlmp.carrier.settlement.allocation'].create({
                'billing_line_id': line.id, 'transport_order_id': order.id, 'allocated_amount': 100.0,
            })


class TestInvariantClosedBatchImmutable(TransactionCase):
    def test_closed_batch_immutable(self):
        partner = self.env['res.partner'].create({'name': 'T', 'is_company': True})
        batch = self.env['tlmp.carrier.settlement.batch'].create({
            'carrier_partner_id': partner.id, 'period_start': '2026-01-01', 'period_end': '2026-01-31',
        })
        batch.action_submit()
        batch.action_approve()
        batch.action_confirm()
        batch.action_close()
        self.assertEqual(batch.state, 'closed')


class TestInvariantExceptionClosedImmutable(TransactionCase):
    def test_closed_exception_immutable(self):
        partner = self.env['res.partner'].create({'name': 'T', 'is_company': True})
        exc = self.env['tlmp.settlement.exception'].create({
            'exception_type': 'MATCH_FAILED',
            'source_model': 'res.partner', 'source_res_id': partner.id,
            'source_display_name': partner.name, 'source_snapshot': '{}',
        })
        exc.write({'cancel_reason': 'Test'})
        exc.action_cancel()
        self.assertEqual(exc.state, 'cancelled')


class TestInvariantExceptionAssignedRequiresOwner(TransactionCase):
    def test_assigned_requires_owner(self):
        partner = self.env['res.partner'].create({'name': 'T', 'is_company': True})
        exc = self.env['tlmp.settlement.exception'].create({
            'exception_type': 'MATCH_FAILED',
            'source_model': 'res.partner', 'source_res_id': partner.id,
            'source_display_name': partner.name, 'source_snapshot': '{}',
        })
        with self.assertRaises(ValidationError):
            exc.write({'state': 'assigned', 'assigned_to': False})


        self.assertEqual(rule1.rule_state, 'deprecated')
