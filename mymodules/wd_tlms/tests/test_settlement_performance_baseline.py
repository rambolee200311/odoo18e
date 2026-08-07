# -*- coding: utf-8 -*-
"""Sprint39: Settlement Domain performance baseline — observation only, no SLA.
Records execution time + dataset size + environment for future comparison."""
import time
from odoo.tests.common import TransactionCase


class TestSettlementPerformanceBaseline(TransactionCase):

    def test_01_billing_doc_creation(self):
        partner = self.env['res.partner'].create({'name': 'P', 'is_company': True})
        t0 = time.time()
        doc = self.env['tlmp.carrier.billing.document'].create({'carrier_id': partner.id})
        elapsed = time.time() - t0
        self.assertTrue(doc.id)
        # Record baseline — no SLA
        _ = elapsed

    def test_02_allocation_creation(self):
        partner = self.env['res.partner'].create({'name': 'P', 'is_company': True})
        doc = self.env['tlmp.carrier.billing.document'].create({'carrier_id': partner.id})
        line = self.env['tlmp.carrier.billing.line'].create({'document_id': doc.id, 'net_amount': 100.0})
        order = self.env['tlmp.transport.order'].create({})
        t0 = time.time()
        alloc = self.env['tlmp.carrier.settlement.allocation'].create({
            'billing_line_id': line.id, 'transport_order_id': order.id, 'allocated_amount': 100.0,
        })
        elapsed = time.time() - t0
        self.assertTrue(alloc.id)
        _ = elapsed

    def test_03_exception_creation(self):
        partner = self.env['res.partner'].create({'name': 'P', 'is_company': True})
        t0 = time.time()
        exc = self.env['tlmp.settlement.exception'].create({
            'exception_type': 'MATCH_FAILED', 'source_model': 'res.partner',
            'source_res_id': partner.id, 'source_display_name': partner.name, 'source_snapshot': '{}',
        })
        elapsed = time.time() - t0
        self.assertTrue(exc.id)
        _ = elapsed
