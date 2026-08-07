from odoo.tests.common import TransactionCase
from odoo.exceptions import ValidationError


class TestTransportReference(TransactionCase):
    """Test Transport Reference CRUD and policies."""

    def setUp(self):
        super().setUp()
        self.Reference = self.env['tlmp.transport.reference']
        self.partner = self.env['res.partner'].create({'name': 'Test Partner'})

    def test_01_create_reference(self):
        ref = self.Reference.create({
            'ref_type': 'tracking_no',
            'ref_value': '1Z999AA10123456784',
            'reference_role': 'identifier',
            'source_system': 'tlms',
        })
        self.assertTrue(ref.id)
        self.assertEqual(ref.ref_type, 'tracking_no')
        self.assertEqual(ref.ref_value, '1Z999AA10123456784')

    def test_02_duplicate_ref_value_allowed(self):
        ref1 = self.Reference.create({
            'ref_type': 'container_no',
            'ref_value': 'MSCU1234567',
            'reference_role': 'equipment',
        })
        ref2 = self.Reference.create({
            'ref_type': 'container_no',
            'ref_value': 'MSCU1234567',
            'reference_role': 'equipment',
        })
        self.assertTrue(ref1.id)
        self.assertTrue(ref2.id)
        self.assertNotEqual(ref1.id, ref2.id)

    def test_03_ref_value_not_empty(self):
        with self.assertRaises(Exception):
            self.Reference.create({
                'ref_type': 'pickup_code',
                'ref_value': '',
                'reference_role': 'identifier',
            })

    def test_04_search_by_ref(self):
        self.Reference.create({
            'ref_type': 'cmr_no', 'ref_value': 'CMR001',
            'reference_role': 'document',
        })
        self.Reference.create({
            'ref_type': 'cmr_no', 'ref_value': 'CMR002',
            'reference_role': 'document',
        })
        results = self.Reference.search_by_ref('cmr_no', 'CMR001')
        self.assertEqual(len(results), 1)
        self.assertEqual(results.ref_value, 'CMR001')

    def test_05_res_model_res_id_association(self):
        ref = self.Reference.create({
            'ref_type': 'shipment_no',
            'ref_value': 'TO-2026-00001',
            'reference_role': 'identifier',
            'source_system': 'tlms',
            'res_model': 'tlmp.transport.order',
            'res_id': 123,
        })
        self.assertEqual(ref.res_model, 'tlmp.transport.order')
        self.assertEqual(ref.res_id, 123)

    def test_06_source_system_default(self):
        ref = self.Reference.create({
            'ref_type': 'booking_no',
            'ref_value': 'BKNG-001',
            'reference_role': 'identifier',
        })
        self.assertEqual(ref.source_system, 'tlms')

    def test_07_reference_role_enum(self):
        ref = self.Reference.create({
            'ref_type': 'container_no',
            'ref_value': 'TEST123',
            'reference_role': 'equipment',
            'source_system': 'external',
        })
        self.assertEqual(ref.reference_role, 'equipment')
        self.assertEqual(ref.source_system, 'external')

    def test_08_active_field(self):
        ref = self.Reference.create({
            'ref_type': 'po_no', 'ref_value': 'PO-001',
            'reference_role': 'identifier',
        })
        self.assertTrue(ref.active)
        ref.write({'active': False})
        self.assertFalse(ref.active)

    def test_09_date_default(self):
        ref = self.Reference.create({
            'ref_type': 'delivery_no', 'ref_value': 'DEL-001',
            'reference_role': 'identifier',
        })
        self.assertTrue(ref.date)
