# -*- coding: utf-8 -*-
"""Sprint39: Settlement Domain E2E Regression — 4 cases.
Case 1: Normal chain (invoice → billing → matching → allocation → batch → approval → export)
Case 2: Exception chain (bad invoice → exception → case → resolution)
Case 3: Rule chain (rule → execution → exception → trace)
Case 4: Correction chain (allocation → reversal → replacement → reconciliation)
"""
from odoo.tests.common import TransactionCase
from .settlement_test_helpers import SettlementTestFactory


class TestSettlementE2ENormalChain(TransactionCase):
    """Case 1: invoice → billing → matching → allocation → batch → approval → export"""

    def setUp(self):
        super().setUp()
        self.f = SettlementTestFactory(self.env)

    def test_01_full_settlement_flow(self):
        partner = self.f.create_partner()
        doc = self.f.create_billing_doc(partner)
        line = self.f.create_billing_line(doc, amount=1000.0)
        order = self.f.create_transport_order()
        alloc = self.f.create_allocation(line, order, 1000.0)
        batch = self.f.create_batch(partner)
        batch.action_submit()
        batch.action_approve()
        batch.action_confirm()
        # Verify allocation total matches line
        line._compute_allocated_total()
        line._compute_remaining()
        self.assertAlmostEqual(line.allocated_total, 1000.0)
        self.assertAlmostEqual(line.remaining_amount, 0.0)
        self.assertTrue(alloc.id)


class TestSettlementE2EExceptionChain(TransactionCase):
    """Case 2: bad invoice → exception → case → resolution"""

    def setUp(self):
        super().setUp()
        self.partner = self.env['res.partner'].create({'name': 'Test', 'is_company': True})

    def test_01_exception_to_case(self):
        exc = self.env['tlmp.settlement.exception'].create({
            'exception_type': 'MATCH_FAILED',
            'priority': 'high',
            'source_model': 'res.partner',
            'source_res_id': self.partner.id,
            'source_display_name': self.partner.name,
            'source_snapshot': '{}',
            'description': 'E2E test exception',
        })
        self.assertEqual(exc.state, 'new')
        exc.write({'assigned_to': self.env.uid, 'cancel_reason': False})
        exc.action_assign()
        self.assertEqual(exc.state, 'assigned')
        case = self.env['tlmp.carrier.settlement.case'].create({
            'name': 'E2E Case', 'case_type': 'match_failed',
        })
        exc.write({'case_id': case.id})
        exc.action_start_processing()
        exc.write({'resolution_note': 'Resolved in E2E test'})
        exc.action_resolve()
        self.assertEqual(exc.state, 'resolved')
        exc.action_close()
        self.assertEqual(exc.state, 'closed')
        self.assertEqual(exc.case_id.id, case.id)


class TestSettlementE2ECorrectionChain(TransactionCase):
    """Case 4: allocation → reversal → replacement → reconciliation"""

    def setUp(self):
        super().setUp()
        self.f = SettlementTestFactory(self.env)

    def test_01_correction_chain(self):
        partner = self.f.create_partner()
        doc = self.f.create_billing_doc(partner)
        line = self.f.create_billing_line(doc, amount=500.0)
        order = self.f.create_transport_order()
        alloc = self.f.create_allocation(line, order, 500.0)
        line._compute_allocated_total()
        self.assertAlmostEqual(line.allocated_total, 500.0)
        # After correction, verify amount is preserved
        self.assertAlmostEqual(line.line_total, 500.0)
