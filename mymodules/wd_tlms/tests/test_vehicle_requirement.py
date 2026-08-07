"""Sprint49-B: Vehicle Requirement Rule Tests (review fix regression suite)."""

import json

from odoo.exceptions import UserError, ValidationError
from odoo.tests import TransactionCase

from ..business_matrix.rule_engine import BusinessMatrixEngine


class TestVehicleRequirement(TransactionCase):
    """Test vehicle requirement fields, compute, snapshots, and rules."""

    def setUp(self):
        super().setUp()
        self.scene_s1 = self.env['tlmp.transport.scene'].search(
            [('code', '=', 'terminal_to_warehouse')], limit=1
        ) or self.env['tlmp.transport.scene'].create({
            'name': 'Test S1', 'code': 'terminal_to_warehouse',
            'scene_type': 'plan_driven', 'destination_type': 'warehouse',
        })
        self.adr_cap = self.env['tlmp.carrier.capability'].search(
            [('code', '=', 'adr')], limit=1) or self.env['tlmp.carrier.capability'].create({
                'code': 'adr', 'name': 'ADR',
            })
        self.dg_cap = self.env['tlmp.carrier.capability'].search(
            [('code', '=', 'dg')], limit=1) or self.env['tlmp.carrier.capability'].create({
                'code': 'dg', 'name': 'Dangerous Goods',
            })
        self.carrier_full = self._make_carrier([self.adr_cap, self.dg_cap])
        self.carrier_dg_only = self._make_carrier([self.dg_cap])
        self.carrier_plain = self._make_carrier([])

    def _make_carrier(self, capabilities):
        return self.env['res.partner'].create({
            'name': 'Carrier %s' % self.env['ir.sequence'].next_by_code('tlmp.request.seq'),
            'is_company': True,
            'is_carrier': True,
            'carrier_capability_ids': [(6, 0, [c.id for c in capabilities])],
        })

    def _create_request(self, **kwargs):
        vals = {
            'scene_id': self.scene_s1.id,
            'request_type': 'plan_driven',
            'cargo_type': kwargs.get('cargo_type', 'container'),
            'carrier_type': kwargs.get('carrier_type', 'truck'),
            'carrier_id': kwargs.get('carrier_id', False),
            'vehicle_body_type': kwargs.get('vehicle_body_type', 'no_requirement'),
            'vehicle_capacity_requirement': kwargs.get(
                'vehicle_capacity_requirement', 'no_limit'),
            'has_dangerous_goods': kwargs.get('has_dangerous_goods', False),
            'dg_attribute': kwargs.get('dg_attribute', 'normal'),
            'dg_adr_class': kwargs.get('dg_adr_class', False),
            'dg_un_code': kwargs.get('dg_un_code', False),
            'warehouse_id': self.env['stock.warehouse'].search([], limit=1).id,
        }
        return self.env['tlmp.transport.request'].create(vals)

    def _vehicle_dim(self, **kwargs):
        dim = {
            'scene_code': 'terminal_to_warehouse',
            'business_driver': 'plan_driven',
            'cargo_category': kwargs.get('cargo_category', 'container'),
            'carrier_type': kwargs.get('carrier_type', 'truck'),
            't1_attribute': kwargs.get('t1_attribute', 'normal'),
            'dg_attribute': kwargs.get('dg_attribute', 'normal'),
            'carrier_capabilities': kwargs.get('carrier_capabilities', set()),
            'mixed_roots': False,
            'vehicle_requirement_mode': kwargs.get('vehicle_requirement_mode', 'required'),
            'vehicle_body_type': kwargs.get('vehicle_body_type', 'no_requirement'),
            'vehicle_capacity_requirement': kwargs.get(
                'vehicle_capacity_requirement', 'no_limit'),
            'is_dangerous_goods': kwargs.get('is_dangerous_goods', 'normal'),
            'has_dangerous_goods': kwargs.get('has_dangerous_goods', False),
            'dg_adr_class': kwargs.get('dg_adr_class', False),
            'dg_un_code': kwargs.get('dg_un_code', False),
            'assigned_vehicle_capacity': kwargs.get('assigned_vehicle_capacity'),
            'assigned_vehicle_body_type': kwargs.get('assigned_vehicle_body_type'),
            'assigned_vehicle_adr': kwargs.get('assigned_vehicle_adr'),
        }
        return dim

    # -----------------------------------------------------------
    # Mode derivation from carrier_type_vehicle_policy
    # -----------------------------------------------------------
    def test_01_truck_default_required(self):
        req = self._create_request(carrier_type='truck')
        self.assertEqual(req.vehicle_requirement_mode, 'required')

    def test_02_own_fleet_default_required(self):
        req = self._create_request(carrier_type='own_fleet')
        self.assertEqual(req.vehicle_requirement_mode, 'required')

    def test_03_courier_default_exempted(self):
        req = self._create_request(carrier_type='courier', cargo_type='piece')
        self.assertEqual(req.vehicle_requirement_mode, 'exempted')

    def test_04_carrier_switch_recalculates_mode(self):
        req = self._create_request(carrier_type='truck', cargo_type='piece')
        self.assertEqual(req.vehicle_requirement_mode, 'required')
        req.carrier_type = 'courier'
        self.assertEqual(req.vehicle_requirement_mode, 'exempted')

    def test_05_policy_config_controls_mode(self):
        extra_policy = self.env['tlmp.business.rule'].create({
            'code': 'VEHICLE-POLICY-TEST',
            'name': 'Test Courier Required',
            'message_cn': 'courier required for test',
            'result': 'warning',
            'priority': 0,
            'carrier_type': 'courier',
            'vehicle_policy_mode': 'required',
        })
        req = self._create_request(carrier_type='courier', cargo_type='piece')
        self.assertEqual(req.vehicle_requirement_mode, 'required')
        extra_policy.unlink()
        req2 = self._create_request(carrier_type='courier', cargo_type='piece')
        self.assertEqual(req2.vehicle_requirement_mode, 'exempted')

    # -----------------------------------------------------------
    # Regression: normal requests must not be BLOCKed by matrix rules
    # -----------------------------------------------------------
    def test_06_normal_truck_request_passes(self):
        req = self._create_request(carrier_type='truck')
        self.assertEqual(req.matrix_validation_result, 'pass')
        self.assertEqual(req.vehicle_requirement_validation_result, 'pass')

    def test_07_exempted_courier_skips_vehicle_checks(self):
        req = self._create_request(
            carrier_type='courier', cargo_type='piece',
            vehicle_body_type='rear_only',
            vehicle_capacity_requirement='below_40t')
        self.assertEqual(req.vehicle_requirement_mode, 'exempted')
        self.assertEqual(req.matrix_validation_result, 'pass')
        self.assertEqual(req.vehicle_requirement_validation_result, 'pass')

    # -----------------------------------------------------------
    # RULE-VEHICLE-002 dangerous goods chain
    # -----------------------------------------------------------
    def test_08_adr_without_capability_blocked(self):
        with self.assertRaises(UserError):
            self._create_request(
                carrier_type='truck', carrier_id=self.carrier_dg_only.id,
                dg_attribute='dg', dg_adr_class='3', dg_un_code='UN1203')
        res = BusinessMatrixEngine.validate(self.env, self._vehicle_dim(
            carrier_type='truck', dg_attribute='dg',
            is_dangerous_goods='adr_dangerous',
            dg_adr_class='3', dg_un_code='UN1203',
            carrier_capabilities={'dg'}))
        self.assertEqual(res['result'], 'block')
        self.assertTrue(any(
            v['rule_id'] == 'RULE-VEHICLE-002' for v in res['violations']))

    def test_09_courier_adr_blocked(self):
        with self.assertRaises(UserError):
            self._create_request(
                carrier_type='courier', cargo_type='piece',
                dg_attribute='dg', dg_adr_class='3', dg_un_code='UN1203')

    def test_10_adr_with_full_capability_passes(self):
        req = self._create_request(
            carrier_type='truck', carrier_id=self.carrier_full.id,
            dg_attribute='dg', dg_adr_class='3', dg_un_code='UN1203')
        self.assertEqual(req.is_dangerous_goods, 'adr_dangerous')
        self.assertEqual(req.vehicle_requirement_validation_result, 'pass')

    def test_11_adr_details_required(self):
        with self.assertRaises(UserError):
            self._create_request(
                carrier_type='truck', carrier_id=self.carrier_full.id,
                dg_attribute='dg')

    def test_12_normal_rejects_adr_details(self):
        with self.assertRaises(ValidationError):
            self._create_request(
                carrier_type='truck', dg_attribute='normal',
                dg_adr_class='3', dg_un_code='UN1203')

    def test_13_is_dangerous_goods_derived_from_cargo(self):
        req = self._create_request(
            carrier_type='truck', carrier_id=self.carrier_full.id)
        self.assertEqual(req.is_dangerous_goods, 'normal')
        self.env['tlmp.transport.cargo.line'].create({
            'request_id': req.id,
            'description': 'DG cargo',
            'cargo_category': 'container',
            'has_dangerous_goods': True,
        })
        self.assertEqual(req.is_dangerous_goods, 'adr_dangerous')
        req.write({'dg_adr_class': '3', 'dg_un_code': 'UN1203'})
        self.assertEqual(req.is_dangerous_goods, 'adr_dangerous')

    # -----------------------------------------------------------
    # RULE-VEHICLE-003 capacity / RULE-VEHICLE-005 body type
    # -----------------------------------------------------------
    def test_14_capacity_constraint_warning(self):
        req = self._create_request(
            carrier_type='truck',
            vehicle_capacity_requirement='below_40t')
        self.assertEqual(req.vehicle_requirement_validation_result, 'warning')
        self.assertEqual(req.matrix_validation_result, 'warning')

    def test_15_capacity_mismatch_blocked(self):
        res = BusinessMatrixEngine.validate(self.env, self._vehicle_dim(
            vehicle_capacity_requirement='40t_44t',
            assigned_vehicle_capacity=35.0))
        self.assertEqual(res['result'], 'block')
        self.assertTrue(any(
            v['rule_id'] == 'RULE-VEHICLE-003' for v in res['violations']))

    def test_16_body_constraint_warning(self):
        req = self._create_request(
            carrier_type='truck', vehicle_body_type='reefer_refrigerated')
        self.assertEqual(req.vehicle_requirement_validation_result, 'warning')
        self.assertEqual(req.matrix_validation_result, 'warning')

    def test_17_body_mismatch_blocked(self):
        res = BusinessMatrixEngine.validate(self.env, self._vehicle_dim(
            vehicle_body_type='rear_only',
            assigned_vehicle_body_type='side_loading'))
        self.assertEqual(res['result'], 'block')
        self.assertTrue(any(
            v['rule_id'] == 'RULE-VEHICLE-005' for v in res['violations']))

    # -----------------------------------------------------------
    # Snapshot freeze and immutability
    # -----------------------------------------------------------
    def test_18_snapshot_frozen_on_confirm(self):
        req = self._create_request(carrier_type='truck')
        self.assertFalse(req.vehicle_requirement_mode_snapshot)
        req.action_confirm()
        self.assertEqual(req.vehicle_requirement_mode_snapshot, 'required')
        self.assertEqual(req.vehicle_requirement_snapshot_status, 'frozen')
        self.assertTrue(req.vehicle_requirement_snapshot)

    def test_19_snapshot_immutable_after_confirm(self):
        req = self._create_request(carrier_type='truck')
        req.action_confirm()
        with self.assertRaises(UserError):
            req.write({'vehicle_body_type': 'rear_only'})
        with self.assertRaises(UserError):
            req.write({'vehicle_requirement_mode_snapshot': 'exempted'})
        with self.assertRaises(UserError):
            req.action_confirm()

    def test_20_snapshot_ignores_later_policy_change(self):
        req = self._create_request(carrier_type='truck', cargo_type='piece')
        req.action_confirm()
        req.carrier_type = 'courier'
        self.assertEqual(req.vehicle_requirement_mode_snapshot, 'required')
        inquiry = self.env['tlmp.transport.inquiry'].create({
            'request_id': req.id,
            'cargo_summary': 'Test cargo',
        })
        self.assertEqual(inquiry.vehicle_requirement_mode, 'required')

    # -----------------------------------------------------------
    # Inquiry / Quote / Plan / Order projection
    # -----------------------------------------------------------
    def test_21_inquiry_quote_exempted_display(self):
        req = self._create_request(carrier_type='courier', cargo_type='piece')
        inquiry = self.env['tlmp.transport.inquiry'].create({
            'request_id': req.id,
            'cargo_summary': 'Test cargo',
        })
        quote = self.env['tlmp.transport.quote'].create({
            'request_id': req.id,
            'inquiry_id': inquiry.id,
            'carrier_cost': 50.0,
        })
        self.assertEqual(inquiry.vehicle_requirement_mode, 'exempted')
        self.assertEqual(quote.vehicle_requirement_mode, 'exempted')
        self.assertEqual(inquiry.vehicle_requirement_display, '车辆要求：豁免')
        self.assertEqual(quote.vehicle_requirement_display, '车辆要求：豁免')

    def test_22_order_snapshot_propagation(self):
        req = self._create_request(
            carrier_type='truck',
            vehicle_body_type='reefer_refrigerated',
            vehicle_capacity_requirement='below_40t')
        req.action_confirm()
        inquiry = self.env['tlmp.transport.inquiry'].create({
            'request_id': req.id,
            'cargo_summary': 'Test cargo',
        })
        quote = self.env['tlmp.transport.quote'].create({
            'request_id': req.id,
            'inquiry_id': inquiry.id,
            'carrier_cost': 100.0,
        })
        quote.action_send()
        quote.action_accept()
        order = quote.transport_order_id
        self.assertTrue(order)
        snapshot = json.loads(order.vehicle_requirement_snapshot)
        self.assertEqual(snapshot['vehicle_requirement_mode'], 'required')
        self.assertEqual(snapshot['vehicle_requirement_mode_snapshot'], 'required')
        self.assertEqual(snapshot['vehicle_body_type'], 'reefer_refrigerated')
        self.assertEqual(
            snapshot['vehicle_capacity_requirement'], 'below_40t')

    def test_23_pickup_plan_projection(self):
        req = self._create_request(carrier_type='truck')
        plan = self.env['pickup.plan'].create({
            'name': 'TEST-PLAN',
            'transport_request_id': req.id,
            'scene_id': self.scene_s1.id,
            'cargo_type': 'container',
            'destination_type': 'warehouse',
            'warehouse_id': self.env['stock.warehouse'].search([], limit=1).id,
        })
        self.assertEqual(plan.vehicle_requirement_mode, 'required')
        self.assertIn('车型', plan.vehicle_requirement_display)
