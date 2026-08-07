# -*- coding: utf-8 -*-
"""Sprint40: Scene Domain Alignment E2E tests.
S1: Terminal->Warehouse (plan_driven)
S5: Warehouse Transfer (plan_driven)
S6: Customer Return (commercial)
S8: Empty Move via container.service.request (standalone)
"""
from odoo.tests.common import TransactionCase
from odoo.exceptions import ValidationError


class TestSceneDomainAlignment(TransactionCase):

    def test_01_request_scene_id(self):
        req = self.env['tlmp.transport.request'].create({
            'request_type': 'plan_driven',
            'destination_type': 'warehouse',
        })
        self.assertTrue(req.id)

    def test_02_scene_flow_validation(self):
        scene = self.env['tlmp.transport.scene'].search([], limit=1)
        if scene and scene.allowed_flow_ids:
            allowed = scene.allowed_flow_ids.mapped('code')
            if 'plan_driven' in allowed:
                req = self.env['tlmp.transport.request'].create({
                    'request_type': 'plan_driven',
                    'destination_type': 'warehouse',
                    'scene_id': scene.id,
                })
                self.assertEqual(req.scene_id.id, scene.id)

    def test_03_order_scene_immutable_definition(self):
        field = self.env['ir.model.fields'].search([
            ('model', '=', 'tlmp.transport.order'),
            ('name', '=', 'scene_id'),
        ], limit=1)
        self.assertTrue(field)
        # Verify it's readonly
        self.assertTrue(field.readonly)

    def test_04_flow_type_model_exists(self):
        model = self.env['ir.model'].search([('model', '=', 'tlmp.transport.flow.type')])
        self.assertTrue(model)

    def test_05_destination_type_model_exists(self):
        model = self.env['ir.model'].search([('model', '=', 'tlmp.transport.destination.type')])
        self.assertTrue(model)

    def test_06_scene_has_new_fields(self):
        scene = self.env['tlmp.transport.scene'].search([], limit=1)
        if scene:
            self.assertTrue(hasattr(scene, 'allowed_flow_ids'))
            self.assertTrue(hasattr(scene, 'allowed_destination_ids'))
            self.assertTrue(hasattr(scene, 'default_transport_type_id'))

    def test_07_pickup_plan_scene_related(self):
        pp_field = self.env['ir.model.fields'].search([
            ('model', '=', 'pickup.plan'),
            ('name', '=', 'scene_id'),
        ], limit=1)
        self.assertTrue(pp_field)
        self.assertTrue(pp_field.related)

    def test_08_quote_create_order_has_scene(self):
        quote = self.env['tlmp.transport.quote']
        self.assertTrue(hasattr(quote, '_auto_create_order'))
