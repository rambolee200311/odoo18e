# -*- coding: utf-8 -*-
"""Sprint39: Settlement Domain Security Matrix — permission isolation."""
from odoo.tests.common import TransactionCase


class TestSecuritySettlementMatrix(TransactionCase):

    def setUp(self):
        super().setUp()
        self.partner = self.env['res.partner'].create({'name': 'T', 'is_company': True})

    def test_02_financier_can_read_only(self):
        user = self.env['res.users'].create({
            'name': 'Fin', 'login': 'fin_s39_%s' % self.id,
            'groups_id': [(6, 0, [self.env.ref('wd_tlms.group_tlm_financier').id])],
        })
        doc = self.env['tlmp.carrier.billing.document'].create({'carrier_id': self.partner.id})
        self.assertTrue(doc.sudo(user=user).read([]))

    def test_03_clerk_can_create_exception(self):
        user = self.env['res.users'].create({
            'name': 'Clerk', 'login': 'clerk_s39_%s' % self.id,
            'groups_id': [(6, 0, [self.env.ref('wd_tlms.group_tlm_settlement_clerk').id])],
        })
        exc = self.env['tlmp.settlement.exception'].sudo(user=user).create({
            'exception_type': 'MATCH_FAILED', 'source_model': 'test',
            'source_res_id': 1, 'source_display_name': 'T', 'source_snapshot': '{}',
        })
        self.assertTrue(exc.id)
