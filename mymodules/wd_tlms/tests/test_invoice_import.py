from odoo.tests.common import TransactionCase

class TestInvoiceImport(TransactionCase):
    def setUp(self):
        super().setUp()
        self.Import = self.env['tlmp.carrier.invoice.import']
        self.ImportLine = self.env['tlmp.carrier.invoice.import.line']
        self.partner = self.env['res.partner'].create({'name': 'Test', 'is_company': True})

    def test_10_create_import_batch(self):
        b = self.Import.create({
            'carrier_partner_id': self.partner.id,
        })
        self.assertTrue(b.id)
        self.assertEqual(b.state, 'draft')

    def test_11_import_state_transition(self):
        b = self.Import.create({'carrier_partner_id': self.partner.id})
        b.action_preview()
        self.assertEqual(b.state, 'preview')
        b.action_cancel()
        self.assertEqual(b.state, 'cancelled')

    def test_12_create_import_line(self):
        b = self.Import.create({'carrier_partner_id': self.partner.id})
        line = self.ImportLine.create({
            'import_id': b.id,
            'line_no': 1,
            'raw_data': '["col1","col2","100"]',
            'parsed_data': '{"amount":100}',
        })
        self.assertTrue(line.id)
        self.assertEqual(line.import_status, 'pending')
        self.assertEqual(len(b.line_ids), 1)

    def test_13_parser_csv(self):
        Parser = self.env['tlmp.invoice.parser']
        rows, enc = Parser.parse_csv(b'col1,col2\nval1,val2\n', encoding='utf-8')
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[1][0], 'val1')

    def test_14_idempotency_check(self):
        Validator = self.env['tlmp.invoice.validator']
        result = Validator.check_idempotency(9999, 'TEST001', 'v1')
        self.assertFalse(result.get('duplicate'))
