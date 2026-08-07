"""Sprint51: Architecture Freeze & Regression Validation tests."""

import json

from odoo.exceptions import UserError
from odoo.tests import TransactionCase

from ..business_matrix.rule_engine import BusinessMatrixEngine


class TestSprint51Freeze(TransactionCase):
    """Freeze baseline regression: rules, workflow, ledger, snapshots."""

    def setUp(self):
        super().setUp()
        self.scene = self.env['tlmp.transport.scene'].search(
            [('code', '=', 'terminal_to_warehouse')], limit=1
        ) or self.env['tlmp.transport.scene'].create({
            'name': 'Test S1', 'code': 'terminal_to_warehouse',
            'scene_type': 'plan_driven', 'destination_type': 'warehouse',
        })
        self.wh = self.env['stock.warehouse'].search([], limit=1)
        self.transport_type = self.env['tlmp.transport.type'].search(
            [], limit=1)

    def _request(self, **kwargs):
        vals = {
            'scene_id': self.scene.id,
            'request_type': 'plan_driven',
            'cargo_type': kwargs.get('cargo_type', 'container'),
            'carrier_type': kwargs.get('carrier_type', 'truck'),
            'vehicle_body_type': kwargs.get('vehicle_body_type', 'no_requirement'),
            'vehicle_capacity_requirement': kwargs.get(
                'vehicle_capacity_requirement', 'no_limit'),
            'dg_attribute': kwargs.get('dg_attribute', 'normal'),
            'has_dangerous_goods': kwargs.get('has_dangerous_goods', False),
            'carrier_id': kwargs.get('carrier_id', False),
            'dg_adr_class': kwargs.get('dg_adr_class', False),
            'dg_un_code': kwargs.get('dg_un_code', False),
            'warehouse_id': self.wh.id,
            'requested_qty': kwargs.get('requested_qty', 100.0),
        }
        return self.env['tlmp.transport.request'].create(vals)

    def _order(self, req, **kwargs):
        return self.env['tlmp.transport.order'].create({
            'request_id': req.id,
            'transport_type_id': self.transport_type.id,
            'state': kwargs.get('state', 'draft'),
            'pickup_plan_id': kwargs.get('pickup_plan_id', False),
            'cargo_weight': kwargs.get('cargo_weight', 100.0),
            'delivered_qty': kwargs.get('delivered_qty', 0.0),
        })

    def _reserve_plan(self, req, assignment=None):
        plan = self.env['pickup.plan'].create({
            'name': 'S51-PLAN',
            'transport_request_id': req.id,
            'scene_id': self.scene.id,
            'cargo_type': 'container',
            'destination_type': 'warehouse',
            'warehouse_id': self.wh.id,
        })
        plan.action_schedule()
        if assignment is not None:
            plan.assignment_context = json.dumps(assignment)
        plan.action_reserve()
        return plan

    def _vehicle_dim(self, **kwargs):
        dim = {
            'scene_code': 'terminal_to_warehouse',
            'business_driver': 'plan_driven',
            'cargo_category': kwargs.get('cargo_category', 'container'),
            'carrier_type': kwargs.get('carrier_type', 'truck'),
            't1_attribute': 'normal',
            'dg_attribute': kwargs.get('dg_attribute', 'normal'),
            'carrier_capabilities': kwargs.get('carrier_capabilities', set()),
            'mixed_roots': False,
            'vehicle_requirement_mode': kwargs.get(
                'vehicle_requirement_mode', 'required'),
            'vehicle_body_type': 'no_requirement',
            'vehicle_capacity_requirement': 'no_limit',
            'is_dangerous_goods': kwargs.get('is_dangerous_goods', 'normal'),
            'has_dangerous_goods': kwargs.get('has_dangerous_goods', False),
            'dg_adr_class': kwargs.get('dg_adr_class', False),
            'dg_un_code': kwargs.get('dg_un_code', False),
            'driver_adr_valid': kwargs.get('driver_adr_valid'),
            'driver_adr_expiry_date': kwargs.get('driver_adr_expiry_date'),
            'assignment_context_required': kwargs.get(
                'assignment_context_required', False),
        }
        return dim

    # ---- Rule Engine freeze cases ----
    def test_01_rule_engine_normal_pass(self):
        res = BusinessMatrixEngine.validate(
            self.env, self._vehicle_dim())
        self.assertEqual(res['result'], 'pass')

    def test_02_rule_engine_adr_no_vehicle_block(self):
        res = BusinessMatrixEngine.validate(self.env, self._vehicle_dim(
            dg_attribute='dg', is_dangerous_goods='adr_dangerous',
            dg_adr_class='3', dg_un_code='UN1203',
            carrier_capabilities=set()))
        self.assertEqual(res['result'], 'block')
        self.assertTrue(any(
            v['rule_id'] == 'RULE-VEHICLE-002' for v in res['violations']))

    def test_03_rule_engine_adr_no_driver_block(self):
        res = BusinessMatrixEngine.validate(self.env, self._vehicle_dim(
            dg_attribute='dg', is_dangerous_goods='adr_dangerous',
            dg_adr_class='3', dg_un_code='UN1203',
            carrier_capabilities={'adr'},
            driver_adr_valid=False,
            driver_adr_expiry_date='2030-01-01',
            assignment_context_required=True))
        self.assertEqual(res['result'], 'block')
        self.assertTrue(any(
            v['rule_id'] == 'RULE-VEHICLE-004' for v in res['violations']))

    def test_04_express_isolation(self):
        # Courier + normal cargo: vehicle rules not executed -> PASS
        res = BusinessMatrixEngine.validate(self.env, self._vehicle_dim(
            carrier_type='courier', cargo_category='piece',
            vehicle_requirement_mode='exempted'))
        self.assertEqual(res['result'], 'pass')
        self.assertFalse(any(
            v['rule_id'].startswith('RULE-VEHICLE')
            for v in res['violations']))
        # Courier + DG: blocked by cargo rule, but NOT by RULE-VEHICLE
        res_dg = BusinessMatrixEngine.validate(self.env, self._vehicle_dim(
            carrier_type='courier', cargo_category='piece',
            vehicle_requirement_mode='exempted',
            dg_attribute='dg', is_dangerous_goods='adr_dangerous'))
        self.assertEqual(res_dg['result'], 'block')
        self.assertTrue(any(
            v['rule_id'] == 'RULE-CARGO-004' for v in res_dg['violations']))
        self.assertFalse(any(
            v['rule_id'].startswith('RULE-VEHICLE')
            for v in res_dg['violations']))
        req = self._request(carrier_type='courier', cargo_type='piece')
        req.action_confirm()
        self.assertEqual(req.vehicle_requirement_validation_result, 'pass')
        plan = self.env['pickup.plan'].create({
            'name': 'EXP-PLAN',
            'transport_request_id': req.id,
            'scene_id': self.scene.id,
            'cargo_type': 'piece',
            'destination_type': 'warehouse',
            'warehouse_id': self.wh.id,
        })
        plan.action_schedule()
        plan.action_reserve()
        self.assertFalse(plan.transport_plan_id.allocation_candidate)
        order = self._order(req, state='confirmed', pickup_plan_id=plan.id)
        order.transition_to_allocated()
        self.assertEqual(order.state, 'allocated')
        self.assertFalse(order.vehicle_allocation_snapshot)

    # ---- Workflow five-model cases ----
    def test_05_request_workflow_full_chain(self):
        req = self._request()
        req.action_submit()
        req.action_process()
        order = self._order(req, state='draft')
        order.write({'state': 'settled', 'delivered_qty': 100.0})
        req.invalidate_recordset()
        req.action_complete()
        self.assertEqual(req.state, 'completed')
        self.assertEqual(req.fulfillment_status, 'completed')

    def test_06_inquiry_close_reason_required(self):
        req = self._request()
        inquiry = self.env['tlmp.transport.inquiry'].create({
            'request_id': req.id,
            'cargo_summary': 'Test',
        })
        inquiry.action_send()
        with self.assertRaises(UserError):
            inquiry.action_close()
        inquiry.action_close(reason='carrier_selected')
        self.assertEqual(inquiry.close_reason, 'carrier_selected')

    def test_07_quote_approval_requires_customer_accept(self):
        req = self._request()
        quote = self.env['tlmp.transport.quote'].create({
            'request_id': req.id,
            'carrier_cost': 100.0,
        })
        quote.action_issue()
        quote.action_approve()
        with self.assertRaises(UserError):
            quote.action_confirm_customer()
        quote.customer_accept = True
        quote.action_confirm_customer()
        self.assertEqual(quote.state, 'confirmed')

    def test_08_plan_reservation_validation(self):
        req = self._request()
        plan = self.env['pickup.plan'].create({
            'name': 'PLAN-VAL',
            'transport_request_id': req.id,
            'scene_id': self.scene.id,
            'cargo_type': 'container',
            'destination_type': 'warehouse',
            'warehouse_id': self.wh.id,
        })
        with self.assertRaises(UserError):
            plan.action_reserve()
        plan.action_schedule()
        with self.assertRaises(UserError):
            plan.action_reserve()
        plan.assignment_context = json.dumps({
            'driver_id': 1,
            'driver_adr_valid': True,
            'expiry_date': '2030-01-01',
        })
        plan.action_reserve(reservation_type='vehicle')
        self.assertEqual(plan.reservation_type, 'vehicle')
        self.assertTrue(plan.transport_plan_id.allocation_candidate_valid)

    def test_09_order_allocated_without_snapshot_blocks(self):
        req = self._request()
        req.action_confirm()
        order = self._order(req, state='confirmed')
        with self.assertRaises(UserError):
            order.transition_to_allocated()

    # ---- Event Ledger cases ----
    def test_10_ledger_first_state_unchanged_on_failure(self):
        req = self._request()
        with self.assertRaises(UserError):
            self.env['tlmp.workflow.engine'].transition(
                req, 'submitted', 'NOT_A_REAL_CODE')
        self.assertEqual(req.state, 'draft')

    def test_11_deprecated_event_code_allowed(self):
        req = self._request()
        code = self.env['tlmp.transport.event.code'].sudo().create({
            'code': 'DEP_TEST',
            'name': 'Deprecated Test',
            'category': 'state',
            'deprecated_at': '2026-08-06 00:00:00',
        })
        self.env['tlmp.workflow.engine'].write_event(
            req, code.code, 'state')
        self.assertTrue(self.env['tlmp.transport.event.ledger'].search_count([
            ('event_type', '=', 'DEP_TEST'),
        ]))

    def test_12_legacy_event_preserved(self):
        req = self._request()
        code = self.env['tlmp.transport.event.code'].sudo().create({
            'code': 'LEGACY_TEST',
            'name': 'Legacy Test',
            'category': 'business',
        })
        event = self.env['tlmp.transport.event.ledger'].create({
            'res_model': 'tlmp.transport.request',
            'res_id': req.id,
            'event_code_id': code.id,
            'event_type': code.code,
            'event_code_status': 'legacy',
            'event_category': 'business',
        })
        self.assertEqual(event.event_code_status, 'legacy')
        self.assertEqual(event.event_type, 'LEGACY_TEST')

    # ---- Snapshot cases ----
    def test_13_snapshot_version_validation(self):
        req = self._request()
        req.action_submit()
        self.assertEqual(req.matrix_version, 'V1.0')
        req_snapshot = json.loads(req.vehicle_requirement_snapshot)
        self.assertTrue(req_snapshot)
        plan = self._reserve_plan(req, {
            'driver_id': 1,
            'driver_adr_valid': True,
            'expiry_date': '2030-01-01',
        })
        order = self._order(req, state='confirmed', pickup_plan_id=plan.id)
        order.transition_to_allocated()
        self.assertEqual(order.matrix_version, req.matrix_version)
        allocation = json.loads(order.vehicle_allocation_snapshot)
        self.assertTrue(allocation.get('valid'))

    def test_14_snapshot_immutability_policy_change(self):
        req = self._request()
        req.action_submit()
        snapshot_before = req.vehicle_requirement_snapshot
        policy = self.env['tlmp.business.rule'].create({
            'code': 'VEHICLE-POLICY-S51',
            'name': 'S51 Policy Change',
            'message_cn': 'truck exempted for test',
            'result': 'warning',
            'priority': 0,
            'carrier_type': 'truck',
            'vehicle_policy_mode': 'exempted',
        })
        req._compute_vehicle_requirement_mode()
        self.assertEqual(req.vehicle_requirement_mode, 'exempted')
        self.assertEqual(req.vehicle_requirement_mode_snapshot, 'required')
        self.assertEqual(req.vehicle_requirement_snapshot, snapshot_before)
        policy.unlink()

    def test_15_snapshot_immutability_rule_change(self):
        req = self._request()
        req.action_confirm()
        plan = self._reserve_plan(req, {
            'driver_id': 1,
            'driver_adr_valid': True,
            'expiry_date': '2030-01-01',
        })
        order = self._order(req, state='confirmed', pickup_plan_id=plan.id)
        order.transition_to_allocated()
        allocation_before = order.vehicle_allocation_snapshot
        matrix_before = order.matrix_snapshot
        rule = self.env['tlmp.business.rule'].create({
            'code': 'RULE-VEHICLE-S51-BLOCK',
            'name': 'S51 Block Rule',
            'message_cn': 'block for freeze test',
            'result': 'block',
            'priority': 5,
            'carrier_type': 'truck',
        })
        res = BusinessMatrixEngine.validate(
            self.env, self._vehicle_dim())
        self.assertEqual(res['result'], 'block')
        self.assertEqual(order.vehicle_allocation_snapshot, allocation_before)
        self.assertEqual(order.matrix_snapshot, matrix_before)
        rule.unlink()

    def test_16_historical_replay_uses_snapshot(self):
        req = self._request()
        req.action_confirm()
        plan = self._reserve_plan(req, {
            'driver_id': 1,
            'driver_adr_valid': True,
            'expiry_date': '2030-01-01',
        })
        order = self._order(req, state='confirmed', pickup_plan_id=plan.id)
        order.transition_to_allocated()
        snapshot = json.loads(order.vehicle_allocation_snapshot)
        self.assertTrue(snapshot.get('valid'))
        rule = self.env['tlmp.business.rule'].create({
            'code': 'RULE-VEHICLE-S51-REPLAY',
            'name': 'S51 Replay Rule',
            'message_cn': 'replay block',
            'result': 'block',
            'priority': 5,
            'carrier_type': 'truck',
        })
        self.assertEqual(
            BusinessMatrixEngine.validate(
                self.env, self._vehicle_dim())['result'], 'block')
        self.assertTrue(json.loads(
            order.vehicle_allocation_snapshot).get('valid'))
        rule.unlink()
