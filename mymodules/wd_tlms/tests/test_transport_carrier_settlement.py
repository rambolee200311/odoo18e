# -*- coding: utf-8 -*-

from odoo.tests.common import TransactionCase
from odoo.exceptions import ValidationError


class TestCarrierChargeType(TransactionCase):
    """Test Charge Type CRUD and constraints."""

    def setUp(self):
        super().setUp()
        self.ChargeType = self.env['tlmp.carrier.charge.type']

    def test_01_create_charge_type(self):
        ct = self.ChargeType.create({
            'code': 'FREIGHT_BASE',
            'name': 'Transport Base',
            'main_category': 'freight',
        })
        self.assertTrue(ct.id)
        self.assertEqual(ct.code, 'FREIGHT_BASE')

    def test_02_code_uppercase(self):
        ct = self.ChargeType.create({
            'code': 'fuel surcharge',
            'name': 'Fuel Surcharge',
            'main_category': 'surcharge',
        })
        self.assertEqual(ct.code, 'FUEL_SURCHARGE')

    def test_03_unique_code(self):
        self.ChargeType.create({
            'code': 'UNIQUE_TEST',
            'name': 'Test',
            'main_category': 'freight',
        })
        with self.assertRaises(Exception):
            self.ChargeType.create({
                'code': 'UNIQUE_TEST',
                'name': 'Duplicate',
                'main_category': 'freight',
            })

    def test_04_read_charge_type(self):
        ct = self.ChargeType.create({
            'code': 'READ_TEST', 'name': 'Read Test', 'main_category': 'freight',
        })
        found = self.ChargeType.search([('code', '=', 'READ_TEST')])
        self.assertEqual(len(found), 1)
        self.assertEqual(found.name, 'Read Test')

    def test_05_update_charge_type(self):
        ct = self.ChargeType.create({
            'code': 'UPDATE_TEST', 'name': 'Old Name', 'main_category': 'freight',
        })
        ct.write({'name': 'New Name'})
        self.assertEqual(ct.name, 'New Name')


class TestBillingDocument(TransactionCase):
    """Test Billing Document CRUD and state machine."""

    def setUp(self):
        super().setUp()
        self.BillingDoc = self.env['tlmp.carrier.billing.document']
        self.BillingLine = self.env['tlmp.carrier.billing.line']
        self.ChargeType = self.env['tlmp.carrier.charge.type']
        self.currency = self.env.ref('base.EUR')
        self.partner = self.env['res.partner'].create({
            'name': 'Test Carrier',
            'is_company': True,
        })
        self.charge_type = self.ChargeType.create({
            'code': 'TEST_FREIGHT', 'name': 'Test Freight', 'main_category': 'freight',
        })

    def test_10_create_billing_document(self):
        doc = self.BillingDoc.create({
            'carrier_id': self.partner.id,
            'currency_id': self.currency.id,
        })
        self.assertTrue(doc.id)
        self.assertEqual(doc.state, 'draft')
        self.assertTrue(doc.name.startswith('TLM-BLD'))

    def test_11_create_billing_document_with_lines(self):
        doc = self.BillingDoc.create({
            'carrier_id': self.partner.id,
            'currency_id': self.currency.id,
        })
        self.BillingLine.create({
            'document_id': doc.id,
            'charge_type_id': self.charge_type.id,
            'net_amount': 100.0,
            'tax': 20.0,
        })
        self.assertEqual(len(doc.line_ids), 1)
        self.assertEqual(doc.total_amount, 120.0)

    def test_12_line_total_compute(self):
        doc = self.BillingDoc.create({
            'carrier_id': self.partner.id,
            'currency_id': self.currency.id,
        })
        line = self.BillingLine.create({
            'document_id': doc.id,
            'charge_type_id': self.charge_type.id,
            'net_amount': 200.0,
            'tax': 50.0,
        })
        self.assertEqual(line.line_total, 250.0)
        line.write({'amount_sign': 'negative'})
        self.assertEqual(line.line_total, -250.0)

    def test_13_confirm_document(self):
        doc = self.BillingDoc.create({
            'carrier_id': self.partner.id,
            'currency_id': self.currency.id,
        })
        doc.action_confirm()
        self.assertEqual(doc.state, 'confirmed')
        self.assertTrue(doc.confirmed_by)
        self.assertTrue(doc.confirmed_date)

    def test_14_cancel_document(self):
        doc = self.BillingDoc.create({
            'carrier_id': self.partner.id,
            'currency_id': self.currency.id,
        })
        doc.action_cancel()
        self.assertEqual(doc.state, 'cancelled')


class TestAllocation(TransactionCase):
    """Test Allocation constraints and audit."""

    def setUp(self):
        super().setUp()
        self.BillingDoc = self.env['tlmp.carrier.billing.document']
        self.BillingLine = self.env['tlmp.carrier.billing.line']
        self.Allocation = self.env['tlmp.carrier.settlement.allocation']
        self.AllocHistory = self.env['tlmp.carrier.allocation.history']
        self.ChargeType = self.env['tlmp.carrier.charge.type']
        self.currency = self.env.ref('base.EUR')
        self.partner = self.env['res.partner'].create({
            'name': 'Carrier Allocation Test',
            'is_company': True,
        })
        self.charge_type = self.ChargeType.create({
            'code': 'ALLOC_FREIGHT', 'name': 'Alloc Freight', 'main_category': 'freight',
        })
        self.order1 = self.env['tlmp.transport.order'].create({
            'name': 'ALLOC-ORDER-001',
        })

    def _create_billing_line(self, amount=500.0):
        doc = self.BillingDoc.create({
            'carrier_id': self.partner.id,
            'currency_id': self.currency.id,
        })
        line = self.BillingLine.create({
            'document_id': doc.id,
            'charge_type_id': self.charge_type.id,
            'net_amount': amount,
        })
        return line

    def test_20_create_allocation(self):
        line = self._create_billing_line()
        alloc = self.Allocation.create({
            'billing_line_id': line.id,
            'charge_type_id': self.charge_type.id,
            'transport_order_id': self.order1.id,
            'allocated_amount': 200.0,
        })
        self.assertTrue(alloc.id)
        self.assertEqual(alloc.allocated_amount, 200.0)

    def test_21_allocation_sum_constraint(self):
        line = self._create_billing_line(100.0)
        self.Allocation.create({
            'billing_line_id': line.id,
            'charge_type_id': self.charge_type.id,
            'transport_order_id': self.order1.id,
            'allocated_amount': 60.0,
        })
        with self.assertRaises(ValidationError):
            self.Allocation.create({
                'billing_line_id': line.id,
                'charge_type_id': self.charge_type.id,
                'transport_order_id': self.order1.id,
                'allocated_amount': 50.0,
            })

    def test_22_unique_allocation(self):
        line = self._create_billing_line(500.0)
        self.Allocation.create({
            'billing_line_id': line.id,
            'charge_type_id': self.charge_type.id,
            'transport_order_id': self.order1.id,
            'allocated_amount': 100.0,
        })
        with self.assertRaises(Exception):
            self.Allocation.create({
                'billing_line_id': line.id,
                'charge_type_id': self.charge_type.id,
                'transport_order_id': self.order1.id,
                'allocated_amount': 100.0,
            })

    def test_23_non_negative_amount(self):
        line = self._create_billing_line(500.0)
        with self.assertRaises(Exception):
            self.Allocation.create({
                'billing_line_id': line.id,
                'charge_type_id': self.charge_type.id,
                'transport_order_id': self.order1.id,
                'allocated_amount': -100.0,
            })

    def test_24_reallocation_creates_history(self):
        line = self._create_billing_line(500.0)
        alloc = self.Allocation.create({
            'billing_line_id': line.id,
            'charge_type_id': self.charge_type.id,
            'transport_order_id': self.order1.id,
            'allocated_amount': 100.0,
        })
        alloc.write({
            'allocated_amount': 150.0,
            'change_reason': 'Updated amount',
        })
        history = self.AllocHistory.search([('allocation_id', '=', alloc.id)])
        self.assertTrue(len(history) >= 2)  # create log + update log
        update_log = history.filtered(lambda h: h.operation_type == 'update')
        self.assertTrue(update_log)
        self.assertEqual(update_log[0].old_amount, 100.0)
        self.assertEqual(update_log[0].new_amount, 150.0)

    def test_25_remaining_amount_compute(self):
        line = self._create_billing_line(200.0)
        self.Allocation.create({
            'billing_line_id': line.id,
            'charge_type_id': self.charge_type.id,
            'transport_order_id': self.order1.id,
            'allocated_amount': 80.0,
        })
        self.assertEqual(line.remaining_amount, 120.0)

    def test_26_billing_line_allocated_total(self):
        line = self._create_billing_line(300.0)
        self.Allocation.create({
            'billing_line_id': line.id,
            'charge_type_id': self.charge_type.id,
            'transport_order_id': self.order1.id,
            'allocated_amount': 100.0,
        })
        self.assertEqual(line.allocated_total, 100.0)
