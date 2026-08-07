# -*- coding: utf-8 -*-
"""Sprint48-A: Cargo Node hierarchy model — tree, constraints, formula, rollup."""
from odoo.tests.common import TransactionCase
from odoo.exceptions import ValidationError


class TestCargoNode(TransactionCase):
    """Cargo Node hierarchy, level constraint, equivalent pallets, rollup."""

    def setUp(self):
        super().setUp()
        self.request = self.env['tlmp.transport.request'].create({
            'request_type': 'commercial',
            'destination_type': 'customer',
            'destination_street': 'Test Street',
            'cargo_type': 'container',
        })
        self.Cargo = self.env['tlmp.transport.cargo.line']

    def _make(self, **kwargs):
        vals = {'request_id': self.request.id, 'description': 'Node'}
        vals.update(kwargs)
        return self.Cargo.create(vals)

    def test_01_valid_hierarchy_tree(self):
        container = self._make(
            description='C001', packaging_level='container', node_type='equipment')
        pallet = self._make(
            description='PAL001', parent_cargo_line_id=container.id,
            packaging_level='handling_unit', qty=10.0,
            pieces_per_pallet=20, pallet_gross_weight_kg=30.0,
            pallet_volume_m3=2.0)
        piece = self._make(
            description='PC1', parent_cargo_line_id=pallet.id,
            packaging_level='piece', qty=100.0,
            piece_gross_weight_kg=2.0, piece_volume_m3=0.12)
        self.assertEqual(container.node_type, 'equipment')
        self.assertEqual(container.pallets_in_container, 1)
        self.assertEqual(piece.parent_cargo_line_id.id, pallet.id)

    def test_02_container_cannot_have_parent(self):
        parent = self._make(description='P', packaging_level='container')
        with self.assertRaises(ValidationError):
            self._make(
                description='C2', parent_cargo_line_id=parent.id,
                packaging_level='container')

    def test_03_cross_level_blocked(self):
        container = self._make(
            description='C001', packaging_level='container')
        with self.assertRaises(ValidationError):
            self._make(
                description='BAD', parent_cargo_line_id=container.id,
                packaging_level='piece')

    def test_04_equivalent_pallets_piece_only(self):
        container = self._make(
            description='C001', packaging_level='container')
        self.assertEqual(container.equivalent_pallets, 0.0)
        piece = self._make(
            description='PC1', packaging_level='piece', qty=100.0,
            piece_gross_weight_kg=2.0, piece_volume_m3=0.12)
        # volume 12 m3 / 1.2 = 10; weight 200 kg / 1000 = 1 -> max = 10
        self.assertEqual(piece.equivalent_pallets, 10.0)

    def test_05_header_rollup_container_tree(self):
        container = self._make(
            description='C001', packaging_level='container')
        pallet1 = self._make(
            description='PAL001', parent_cargo_line_id=container.id,
            packaging_level='handling_unit', qty=10.0,
            pieces_per_pallet=20, pallet_gross_weight_kg=30.0,
            pallet_volume_m3=2.0)
        self._make(
            description='PAL002', parent_cargo_line_id=container.id,
            packaging_level='handling_unit', qty=10.0,
            pieces_per_pallet=20, pallet_gross_weight_kg=30.0,
            pallet_volume_m3=2.0)
        self._make(
            description='PC1', parent_cargo_line_id=pallet1.id,
            packaging_level='piece', qty=100.0,
            piece_gross_weight_kg=2.0, piece_volume_m3=0.12)
        self.request._onchange_cargo_line_totals()
        self.assertEqual(self.request.pallet_count, 20)
        self.assertEqual(self.request.package_count, 500)
        self.assertEqual(self.request.cargo_weight, 500.0)
        self.assertEqual(self.request.cargo_volume, 32.0)

    def test_06_source_traceability(self):
        line = self._make(
            description='TRACE', packaging_level='piece',
            source_module='wms', source_model='stock.move.line',
            source_id=88992, source_line_id=88993)
        self.assertEqual(line.source_module, 'wms')
        self.assertEqual(line.source_model, 'stock.move.line')
        self.assertEqual(line.source_id, 88992)
        self.assertEqual(line.source_line_id, 88993)
