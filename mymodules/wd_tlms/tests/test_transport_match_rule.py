from odoo.tests.common import TransactionCase
from odoo.exceptions import ValidationError


class TestMatchRule(TransactionCase):
    """Test Match Rule CRUD and priority."""

    def setUp(self):
        super().setUp()
        self.MatchRule = self.env['tlmp.carrier.match.rule']

    def test_01_create_rule(self):
        rule = self.MatchRule.create({
            'name': 'Container Match',
            'sequence': 10,
            'match_ref_type': 'container_no',
            'match_ref_value': 'MSCU1234567',
        })
        self.assertTrue(rule.id)
        self.assertEqual(rule.match_ref_type, 'container_no')

    def test_02_rule_sequence_order(self):
        r1 = self.MatchRule.create({
            'name': 'Low Priority', 'sequence': 20,
            'match_ref_type': 'container_no', 'match_ref_value': 'C001',
        })
        r2 = self.MatchRule.create({
            'name': 'High Priority', 'sequence': 10,
            'match_ref_type': 'bl_no', 'match_ref_value': 'BL001',
        })
        rules = self.MatchRule.search([], order='sequence, id')
        self.assertEqual(rules[0].id, r2.id)
        self.assertEqual(rules[1].id, r1.id)

    def test_03_rule_carrier_optional(self):
        rule = self.MatchRule.create({
            'name': 'Global Rule', 'sequence': 5,
            'match_ref_type': 'tracking_no', 'match_ref_value': 'TRK001',
        })
        self.assertFalse(rule.carrier_id)
        self.assertTrue(rule.is_active)


class TestMatchSuggestion(TransactionCase):
    """Test Suggestion lifecycle."""

    def setUp(self):
        super().setUp()
        self.Suggestion = self.env['tlmp.carrier.match.suggestion']
        self.History = self.env['tlmp.carrier.matching.history']
        self.partner = self.env['res.partner'].create({'name': 'Test Partner'})
        self.currency = self.env.ref('base.EUR')
        self.charge_type = self.env['tlmp.carrier.charge.type'].create({
            'code': 'MATCH_TEST', 'name': 'Match Test', 'main_category': 'freight',
        })
        self.doc = self.env['tlmp.carrier.billing.document'].create({
            'carrier_id': self.partner.id,
            'currency_id': self.currency.id,
        })
        self.line = self.env['tlmp.carrier.billing.line'].create({
            'document_id': self.doc.id,
            'charge_type_id': self.charge_type.id,
            'net_amount': 100.0,
        })
        self.order = self.env['tlmp.transport.order'].create({})

    def test_10_create_suggestion(self):
        ref_str = 'tlmp.transport.order,%d' % self.order.id
        sug = self.Suggestion.create({
            'billing_line_id': self.line.id,
            'candidate_reference': ref_str,
            'confidence_score': 0.85,
            'confidence_source': 'container_exact',
        })
        self.assertTrue(sug.id)
        self.assertEqual(sug.state, 'draft')

    def test_11_confirm_suggestion(self):
        ref_str = 'tlmp.transport.order,%d' % self.order.id
        sug = self.Suggestion.create({
            'billing_line_id': self.line.id,
            'candidate_reference': ref_str,
            'confidence_score': 0.95,
            'confidence_source': 'bl_exact',
        })
        sug.action_confirm()
        self.assertEqual(sug.state, 'confirmed')
        history = self.History.search([('suggestion_id', '=', sug.id)])
        self.assertTrue(history)

    def test_12_reject_suggestion(self):
        ref_str = 'tlmp.transport.order,%d' % self.order.id
        sug = self.Suggestion.create({
            'billing_line_id': self.line.id,
            'candidate_reference': ref_str,
            'confidence_score': 0.50,
            'confidence_source': 'tracking_exact',
        })
        sug.action_reject()
        self.assertEqual(sug.state, 'rejected')


class TestMatchService(TransactionCase):
    """Test Match Service suggestion generation."""

    def setUp(self):
        super().setUp()
        self.MatchService = self.env['tlmp.transport.match.service']
        self.MatchRule = self.env['tlmp.carrier.match.rule']
        self.Reference = self.env['tlmp.transport.reference']
        self.partner = self.env['res.partner'].create({'name': 'Test Partner'})
        self.currency = self.env.ref('base.EUR')
        self.doc = self.env['tlmp.carrier.billing.document'].create({
            'carrier_id': self.partner.id,
            'currency_id': self.currency.id,
        })
        self.charge_type = self.env['tlmp.carrier.charge.type'].create({
            'code': 'SVC_TEST', 'name': 'Service Test', 'main_category': 'freight',
        })
        self.line = self.env['tlmp.carrier.billing.line'].create({
            'document_id': self.doc.id,
            'charge_type_id': self.charge_type.id,
            'net_amount': 100.0,
        })

    def test_20_suggest_no_rule(self):
        result = self.MatchService.suggest_matches(self.line)
        self.assertEqual(len(result), 0)

    def test_21_suggest_with_reference(self):
        order = self.env['tlmp.transport.order'].create({})
        self.Reference.create({
            'ref_type': 'shipment_no',
            'ref_value': order.name,
            'reference_role': 'identifier',
            'source_system': 'tlms',
            'res_model': 'tlmp.transport.order',
            'res_id': order.id,
        })
        self.MatchRule.create({
            'name': 'Shipment Match',
            'sequence': 10,
            'match_ref_type': 'shipment_no',
            'match_ref_value': order.name,
        })
        result = self.MatchService.suggest_matches(self.line)
        self.assertTrue(len(result) >= 1)
        self.assertEqual(result[0]['candidate_reference_model'], 'tlmp.transport.order')
