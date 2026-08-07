"""Settlement test helpers — pure Python factory, not Odoo AbstractModel."""


class SettlementTestFactory:
    """Create settlement test data. Used by all test_settlement_* files."""

    def __init__(self, env):
        self.env = env

    def create_partner(self, name='Test Carrier'):
        return self.env['res.partner'].create({
            'name': name, 'is_company': True,
        })

    def create_currency(self):
        return self.env.ref('base.EUR')

    def create_charge_type(self, code='TEST_FREIGHT'):
        return self.env['tlmp.carrier.charge.type'].create({
            'code': code, 'name': code, 'main_category': 'freight',
        })

    def create_billing_doc(self, partner, currency=None):
        if not currency:
            currency = self.create_currency()
        return self.env['tlmp.carrier.billing.document'].create({
            'carrier_id': partner.id,
            'currency_id': currency.id,
        })

    def create_billing_line(self, doc, charge_type=None, amount=100.0):
        if not charge_type:
            charge_type = self.create_charge_type()
        return self.env['tlmp.carrier.billing.line'].create({
            'document_id': doc.id,
            'charge_type_id': charge_type.id,
            'net_amount': amount,
        })

    def create_transport_order(self):
        return self.env['tlmp.transport.order'].create({})

    def create_allocation(self, line, order, amount):
        return self.env['tlmp.carrier.settlement.allocation'].create({
            'billing_line_id': line.id,
            'transport_order_id': order.id,
            'allocated_amount': amount,
        })

    def create_match_rule(self, ref_type='shipment_no', ref_value='', sequence=10):
        return self.env['tlmp.carrier.match.rule'].create({
            'name': 'Test Rule %s' % ref_type,
            'sequence': sequence,
            'match_ref_type': ref_type,
            'match_ref_value': ref_value or 'TEST',
        })

    def create_batch(self, partner, start='2026-01-01', end='2026-01-31'):
        return self.env['tlmp.carrier.settlement.batch'].create({
            'carrier_partner_id': partner.id,
            'period_start': start,
            'period_end': end,
        })

    def create_reference(self, ref_type, ref_value, order):
        return self.env['tlmp.transport.reference'].create({
            'ref_type': ref_type,
            'ref_value': ref_value,
            'reference_role': 'identifier',
            'source_system': 'tlms',
            'res_model': 'tlmp.transport.order',
            'res_id': order.id,
        })
