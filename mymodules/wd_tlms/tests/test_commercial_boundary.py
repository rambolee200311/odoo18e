"""Sprint51: Commercial Boundary Regression (freeze, no customer.order)."""

from odoo.tests import TransactionCase


class TestCommercialBoundary(TransactionCase):
    """Verify Request is demand input and Order is supplier execution."""

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
        self.carrier = self.env['res.partner'].create({
            'name': 'CB Carrier',
            'is_company': True,
            'is_carrier': True,
        })

    def _request(self):
        return self.env['tlmp.transport.request'].create({
            'scene_id': self.scene.id,
            'request_type': 'plan_driven',
            'cargo_type': 'container',
            'warehouse_id': self.wh.id,
        })

    def test_request_has_no_customer_order_id(self):
        req = self._request()
        self.assertNotIn('customer_order_id', req._fields)
        self.assertEqual(req.state, 'draft')

    def test_order_is_supplier_execution(self):
        req = self._request()
        order = self.env['tlmp.transport.order'].create({
            'request_id': req.id,
            'transport_type_id': self.transport_type.id,
            'carrier_id': self.carrier.id,
            'fleet_operation_mode': 'subcontracted',
        })
        self.assertNotIn('customer_order_id', order._fields)
        self.assertIn('carrier_id', order._fields)
        self.assertEqual(order.request_id.id, req.id)
        self.assertTrue(order.carrier_id)

    def test_request_order_counts_differ(self):
        req = self._request()
        self.assertEqual(
            self.env['tlmp.transport.request'].search_count(
                [('id', '=', req.id)]), 1)
        self.assertEqual(
            self.env['tlmp.transport.order'].search_count(
                [('request_id', '=', req.id)]), 0)
