# -*- coding: utf-8 -*-
"""Sprint49: Business Matrix rule engine positive/negative/conflict tests."""
from odoo.tests.common import TransactionCase
from odoo.exceptions import UserError, ValidationError


class TestBusinessMatrix(TransactionCase):
    """8 positive + 7 negative + 1 conflict matrix cases."""

    def setUp(self):
        super().setUp()
        Capability = self.env['tlmp.carrier.capability']
        self.cap_t1 = Capability.create({'code': 't1', 'name': 'T1'})
        self.cap_dg = Capability.create({'code': 'dg', 'name': 'DG'})
        self.cap_adr = Capability.create({'code': 'adr', 'name': 'ADR'})
        self.carrier_truck = self.env['res.partner'].create({
            'name': 'Truck', 'is_carrier': True,
            'carrier_type': 'subcontracted'})
        self.carrier_own = self.env['res.partner'].create({
            'name': 'Own', 'is_carrier': True,
            'carrier_type': 'own_fleet'})
        self.carrier_courier = self.env['res.partner'].create({
            'name': 'Courier', 'is_carrier': True})
        self.carrier_t1 = self.env['res.partner'].create({
            'name': 'T1Carrier', 'is_carrier': True,
            'carrier_capability_ids': [(6, 0, [self.cap_t1.id])]})
        self.carrier_dg = self.env['res.partner'].create({
            'name': 'DGCarrier', 'is_carrier': True,
            'carrier_capability_ids': [
                (6, 0, [self.cap_dg.id, self.cap_adr.id])]})

    def _make(self, **kw):
        vals = {
            'request_type': 'commercial',
            'business_driver': 'commercial',
            'destination_type': 'customer',
            'destination_street': 'Test Street',
            'cargo_type': 'pallet',
            'carrier_type': 'truck',
        }
        vals.update(kw)
        return self.env['tlmp.transport.request'].create(vals)

    def test_01_positive_combos(self):
        combos = [
            {'cargo_type': 'container', 'business_driver': 'plan_driven',
             'carrier_type': 'own_fleet'},
            {'cargo_type': 'container', 'business_driver': 'plan_driven',
             'carrier_type': 'truck'},
            {'cargo_type': 'pallet', 'business_driver': 'plan_driven',
             'carrier_type': 'own_fleet'},
            {'cargo_type': 'pallet', 'business_driver': 'plan_driven',
             'carrier_type': 'truck'},
            {'cargo_type': 'pallet', 'business_driver': 'commercial',
             'carrier_type': 'courier'},
            {'cargo_type': 'piece', 'business_driver': 'commercial',
             'carrier_type': 'courier'},
            {'cargo_type': 'container', 'business_driver': 'plan_driven',
             'carrier_type': 'truck', 't1_attribute': 't1',
             'carrier_id': self.carrier_t1.id},
            {'cargo_type': 'pallet', 'business_driver': 'plan_driven',
             'carrier_type': 'own_fleet', 'dg_attribute': 'dg',
             'carrier_id': self.carrier_dg.id,
             'dg_adr_class': '3', 'dg_un_code': 'UN1203'},
        ]
        for combo in combos:
            req = self._make(**combo)
            self.assertEqual(
                req.matrix_validation_result, 'pass',
                msg='expected pass for %s' % combo)

    def test_02_negative_c1_d3(self):
        with self.assertRaises(UserError):
            self._make(cargo_type='container', carrier_type='courier')

    def test_03_negative_c3_e1(self):
        with self.assertRaises(UserError):
            self._make(cargo_type='piece', t1_attribute='t1')

    def test_04_negative_d3_e1(self):
        with self.assertRaises(UserError):
            self._make(carrier_type='courier', t1_attribute='t1')

    def test_05_negative_d3_f1(self):
        with self.assertRaises(UserError):
            self._make(carrier_type='courier', dg_attribute='dg')

    def test_06_negative_e1_no_t1_capability(self):
        with self.assertRaises(UserError):
            self._make(t1_attribute='t1', carrier_id=self.carrier_truck.id)

    def test_07_negative_f1_no_dg_capability(self):
        with self.assertRaises(UserError):
            self._make(dg_attribute='dg', carrier_id=self.carrier_truck.id)

    def test_08_negative_mixed_cargo_root(self):
        req = self._make(cargo_type='container')
        with self.assertRaises(ValidationError):
            self.env['tlmp.transport.cargo.line'].create({
                'request_id': req.id, 'description': 'C2 line',
                'packaging_level': 'handling_unit',
                'cargo_category': 'pallet'})

    def test_09_conflict_all_violations_collected(self):
        with self.assertRaises(UserError) as cm:
            self._make(carrier_type='courier', t1_attribute='t1',
                       dg_attribute='dg')
        msg = str(cm.exception)
        self.assertIn('快递公司无跨境T1报关配套能力', msg)
        self.assertIn('普通快递无危化运输资质', msg)

    def test_10_evaluate_service(self):
        service = self.env['tlmp.business.matrix']
        res_block = service.evaluate({
            'cargo_category': 'container', 'carrier_type': 'courier',
            't1_attribute': 'normal', 'dg_attribute': 'normal',
            'carrier_capabilities': set(), 'mixed_roots': False})
        self.assertEqual(res_block['result'], 'block')
        res_pass = service.evaluate({
            'cargo_category': 'container', 'carrier_type': 'truck',
            't1_attribute': 'normal', 'dg_attribute': 'normal',
            'carrier_capabilities': set(), 'mixed_roots': False})
        self.assertEqual(res_pass['result'], 'pass')

    def test_11_warning_rule(self):
        req = self._make(cargo_type='piece', carrier_type='truck',
                         dg_attribute='dg', carrier_id=self.carrier_dg.id,
                         dg_adr_class='3', dg_un_code='UN1203')
        self.assertEqual(req.matrix_validation_result, 'warning')
        self.assertIn('RULE-COMPLIANCE-001', req.matrix_validation_violations)
