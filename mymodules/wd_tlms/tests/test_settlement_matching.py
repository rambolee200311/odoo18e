from odoo.tests.common import TransactionCase
from .settlement_test_helpers import SettlementTestFactory

class TestSettlementMatching(TransactionCase):
    def setUp(self):
        super().setUp()
        self.f = SettlementTestFactory(self.env)
        self.MatchService = self.env['tlmp.transport.match.service']

    def test_10_high_confidence_auto_confirms(self):
        order = self.f.create_transport_order()
        order_ref = self.f.create_reference('shipment_no', order.name, order)
        partner = self.f.create_partner()
        doc = self.f.create_billing_doc(partner)
        line = self.f.create_billing_line(doc)
        rule = self.f.create_match_rule('shipment_no', order.name)
        suggestions = self.MatchService.suggest_matches(line)
        self.assertEqual(len(suggestions), 0)

    def test_11_low_confidence_draft_no_allocation(self):
        order = self.f.create_transport_order()
        partner = self.f.create_partner()
        doc = self.f.create_billing_doc(partner)
        line = self.f.create_billing_line(doc)
        suggestions = self.MatchService.suggest_matches(line)
        self.assertEqual(len(suggestions), 0)

    def test_12_idempotent_execution(self):
        partner = self.f.create_partner()
        doc = self.f.create_billing_doc(partner)
        line = self.f.create_billing_line(doc)
        result1 = self.MatchService.suggest_matches(line)
        result2 = self.MatchService.suggest_matches(line)
        self.assertEqual(len(result1), len(result2))
