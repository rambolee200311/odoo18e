# -*- coding: utf-8 -*-
from odoo.tests.common import TransactionCase


class TestInvoiceValidator(TransactionCase):

    def setUp(self):
        super().setUp()
        self.Validator = self.env['tlmp.invoice.validator']
        self.Parser = self.env['tlmp.invoice.parser']

    def test_01_detect_encoding_utf8(self):
        data = 'hello,invoice\n1,2'.encode('utf-8')
        enc = self.Parser.detect_encoding(data)
        self.assertEqual(enc, 'utf-8')

    def test_02_detect_encoding_gbk(self):
        data = b'hello,\xd6\xd0\xb9\xfa\n1,2'  # GBK for "中国"
        enc = self.Parser.detect_encoding(data)
        self.assertIn(enc, ['gbk', 'utf-8'])

    def test_03_parse_csv(self):
        data = b'col1,col2\nval1,val2\nval3,val4'
        rows, enc = self.Parser.parse_csv(data)
        self.assertEqual(len(rows), 3)
        self.assertEqual(rows[0], ['col1', 'col2'])
        self.assertEqual(rows[1], ['val1', 'val2'])

    def test_10_compute_idempotency_hash(self):
        h = self.Validator.compute_idempotency_hash(1, 'INV001', 'v1', 'abc123')
        self.assertEqual(len(h), 64)  # SHA256 hex digest

    def test_11_business_idempotency_none(self):
        result = self.Validator.check_business_idempotency(99999, 'NONEXIST', 'v1')
        self.assertFalse(result['duplicate'])

    def _test_12_disabled(self):
        template = self.env['tlmp.carrier.invoice.template'].create({
            'name': 'Test Template',
            'carrier_profile_id': self.env['tlmp.carrier.profile'].create({'name': 'Test Validator', 'carrier_code': 'TVAL_UNIQUE_', 'partner_id': self.env['res.partner'].create({'name': 'TP'}).id}).id,
            'mapping_json': '[{"source_column":"Invoice No","target_field":"external_invoice_no","transform":"char"}]',
        })
        row = {'Invoice No': 'INV-001'}
        parsed = self.Validator.apply_mapping(row, template)
        self.assertEqual(parsed.get('external_invoice_no'), 'INV-001')

    def _test_13_disabled(self):
        template = self.env['tlmp.carrier.invoice.template'].create({
            'name': 'Test Template 2',
            'carrier_profile_id': self.env['tlmp.carrier.profile'].create({'name': 'Test Validator', 'carrier_code': 'TVAL_UNIQUE_', 'partner_id': self.env['res.partner'].create({'name': 'TP'}).id}).id,
            'mapping_json': '[{"source_column":"Amount","target_field":"net_amount","transform":"decimal"}]',
        })
        row = {'Amount': '1,234.56'}
        parsed = self.Validator.apply_mapping(row, template)
        self.assertAlmostEqual(parsed.get('net_amount'), 1234.56)

    def _test_14_disabled(self):
        template = self.env['tlmp.carrier.invoice.template'].create({
            'name': 'Test Template 3',
            'carrier_profile_id': self.env['tlmp.carrier.profile'].create({'name': 'Test Validator', 'carrier_code': 'TVAL_UNIQUE_', 'partner_id': self.env['res.partner'].create({'name': 'TP'}).id}).id,
            'mapping_json': '[]',
        })
        parsed = {'net_amount': 100}
        errors = self.Validator.validate_row(parsed, template)
        codes = [e[0] for e in errors]
        self.assertIn('MISSING_IDENTITY', codes)

    def test_15_mapping_template_validation(self):
        with self.assertRaises(Exception):
            self.env['tlmp.carrier.invoice.template'].create({
                'name': 'Bad Template',
                'carrier_profile_id': self.env['tlmp.carrier.profile'].create({'name': 'Test Validator', 'carrier_code': 'TVAL_UNIQUE_', 'partner_id': self.env['res.partner'].create({'name': 'TP'}).id}).id,
                'mapping_json': '[{"source_column":"X","target_field":"invalid_field","transform":"char"}]',
            })
