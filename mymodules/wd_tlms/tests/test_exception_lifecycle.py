# -*- coding: utf-8 -*-
"""Settlement Exception lifecycle and invariant tests."""
from odoo.tests.common import TransactionCase
from odoo.exceptions import ValidationError


class TestExceptionLifecycle(TransactionCase):

    def setUp(self):
        super().setUp()
        self.partner = self.env['res.partner'].create({
            'name': 'Test Carrier', 'is_company': True,
        })
        self.exception = self.env['tlmp.settlement.exception'].create({
            'exception_type': 'MATCH_FAILED',
            'priority': 'high',
            'description': 'Test exception',
            'source_model': 'res.partner',
            'source_res_id': self.partner.id,
            'source_display_name': self.partner.name,
            'source_snapshot': '{"test": true}',
        })

    def test_01_state_new(self):
        self.assertEqual(self.exception.state, 'new')

    def test_02_assign_requires_owner(self):
        with self.assertRaises(ValidationError):
            self.exception.write({'state': 'assigned', 'assigned_to': False})

    def test_03_assign_sets_state(self):
        self.exception.write({'assigned_to': self.env.uid})
        self.exception.action_assign()
        self.assertEqual(self.exception.state, 'assigned')

    def test_04_processing_to_resolved_requires_note(self):
        self.exception.write({'assigned_to': self.env.uid})
        self.exception.action_assign()
        case = self.env['tlmp.carrier.settlement.case'].create({
            'name': 'Test Case', 'case_type': 'match_failed',
        })
        self.exception.write({'case_id': case.id})
        self.exception.action_start_processing()
        with self.assertRaises(ValidationError):
            self.exception.action_resolve()

    def test_05_full_lifecycle(self):
        self.exception.write({'assigned_to': self.env.uid})
        self.exception.action_assign()
        case = self.env['tlmp.carrier.settlement.case'].create({
            'name': 'Test Case', 'case_type': 'match_failed',
        })
        self.exception.write({'case_id': case.id})
        self.exception.action_start_processing()
        self.exception.write({'resolution_note': 'Resolved by test'})
        self.exception.action_resolve()
        self.assertEqual(self.exception.state, 'resolved')
        self.exception.action_close()
        self.assertEqual(self.exception.state, 'closed')

    def test_06_cancelled_requires_reason(self):
        with self.assertRaises(ValidationError):
            self.exception.action_cancel()
        self.exception.write({'cancel_reason': 'Test cancellation'})
        self.exception.action_cancel()
        self.assertEqual(self.exception.state, 'cancelled')


class TestExceptionAutoResolution(TransactionCase):

    def test_01_duplicate_invoice_auto_resolves(self):
        partner = self.env['res.partner'].create({'name': 'Test', 'is_company': True})
        exc = self.env['tlmp.settlement.exception'].create({
            'exception_type': 'DUPLICATE_INVOICE',
            'priority': 'normal',
            'description': 'Duplicate test',
            'source_model': 'res.partner',
            'source_res_id': partner.id,
            'source_display_name': partner.name,
            'source_snapshot': '{}',
        })
        exc.write({'resolution_note': 'Auto test'})
        exc.action_auto_resolve()
        self.assertEqual(exc.state, 'closed')
        self.assertEqual(exc.resolution_mode, 'auto')

    def test_02_non_duplicate_cannot_auto_resolve(self):
        partner = self.env['res.partner'].create({'name': 'Test', 'is_company': True})
        exc = self.env['tlmp.settlement.exception'].create({
            'exception_type': 'MATCH_FAILED',
            'source_model': 'res.partner',
            'source_res_id': partner.id,
            'source_display_name': partner.name,
            'source_snapshot': '{}',
        })
        with self.assertRaises(ValidationError):
            exc.action_auto_resolve()


class TestExceptionCaseLink(TransactionCase):

    def test_01_exception_links_to_case(self):
        partner = self.env['res.partner'].create({'name': 'Test', 'is_company': True})
        exc = self.env['tlmp.settlement.exception'].create({
            'exception_type': 'MATCH_FAILED',
            'source_model': 'res.partner',
            'source_res_id': partner.id,
            'source_display_name': partner.name,
            'source_snapshot': '{}',
        })
        case = self.env['tlmp.carrier.settlement.case'].create({
            'name': 'Test Case', 'case_type': 'match_failed',
        })
        exc.write({'case_id': case.id})
        self.assertEqual(exc.case_id.id, case.id)
        self.assertIn(exc.id, case.exception_ids.ids)


class TestExceptionSLA(TransactionCase):

    def test_01_sla_deadline_computed(self):
        partner = self.env['res.partner'].create({'name': 'Test', 'is_company': True})
        exc = self.env['tlmp.settlement.exception'].create({
            'exception_type': 'MATCH_FAILED',
            'priority': 'urgent',
            'source_model': 'res.partner',
            'source_res_id': partner.id,
            'source_display_name': partner.name,
            'source_snapshot': '{}',
        })
        self.assertTrue(exc.sla_deadline)
        self.assertIn(exc.sla_status, ('on_track', 'at_risk', 'overdue'))


class TestExceptionTraceability(TransactionCase):

    def test_01_source_reference_required(self):
        with self.assertRaises(ValidationError):
            self.env['tlmp.settlement.exception'].create({
                'exception_type': 'MATCH_FAILED',
                'source_model': 'test',
            })
