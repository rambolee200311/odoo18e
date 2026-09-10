# -*- coding: utf-8 -*-
# © 2024 Wukong Digital. License LGPL-3.
"""Tests for PickerColumn ORM constraints and field-type invariants (INT-ARP-001 §8.1)."""
from odoo.exceptions import ValidationError
from odoo.tests.common import TransactionCase

from odoo.addons.wd_web_advanced_record_picker.models.picker_column import (
    DISPLAY_FIELD_TYPES,
    FILTER_FIELD_TYPES,
)


class TestPickerColumn(TransactionCase):
    """Column-focused constraint and field-type invariant tests."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Profile = cls.env["advanced.record.picker.profile"]
        cls.Column = cls.env["advanced.record.picker.column"]
        cls.partner_model = cls.env["ir.model"]._get("res.partner")
        cls.user_model = cls.env["ir.model"]._get("res.users")
        cls.partner_name = cls.env["ir.model.fields"]._get("res.partner", "name")
        cls.partner_email = cls.env["ir.model.fields"]._get("res.partner", "email")

    def _profile(self, **values):
        defaults = {
            "name": "Column Test Profile",
            "code": "col_test_base",
            "model_id": self.partner_model.id,
        }
        defaults.update(values)
        return self.Profile.create(defaults)

    # ── §8.1: FILTER_FIELD_TYPES ⊆ DISPLAY_FIELD_TYPES ────────────────────
    def test_filter_types_subset_of_display_types(self):
        """FILTER_FIELD_TYPES must be a proper subset of DISPLAY_FIELD_TYPES."""
        self.assertTrue(
            FILTER_FIELD_TYPES.issubset(DISPLAY_FIELD_TYPES),
            "FILTER_FIELD_TYPES must be a subset of DISPLAY_FIELD_TYPES",
        )
        # monetary is a Display type but must NOT be a Filter type
        self.assertIn("monetary", DISPLAY_FIELD_TYPES)
        self.assertNotIn("monetary", FILTER_FIELD_TYPES)
        # binary/html are not allowed in either set
        for forbidden in ("binary", "one2many", "many2many", "html", "json"):
            self.assertNotIn(forbidden, DISPLAY_FIELD_TYPES)

    # ── §8.1: valid column states ───────────────────────────────────────────
    def test_display_only_column_succeeds(self):
        """visible=True, filterable=False (Display Only) is accepted."""
        profile = self._profile(code="col_display_only")
        col = self.Column.create(
            {
                "profile_id": profile.id,
                "field_id": self.partner_name.id,
                "visible": True,
                "filterable": False,
            }
        )
        self.assertTrue(col.visible)
        self.assertFalse(col.filterable)

    def test_display_filterable_column_succeeds(self):
        """visible=True, filterable=True (Display + Filterable) is accepted."""
        profile = self._profile(code="col_display_filterable")
        col = self.Column.create(
            {
                "profile_id": profile.id,
                "field_id": self.partner_name.id,
                "visible": True,
                "filterable": True,
            }
        )
        self.assertTrue(col.visible)
        self.assertTrue(col.filterable)

    # ── §8.1: model_id required ─────────────────────────────────────────────
    def test_profile_model_id_required(self):
        """Creating a Profile without model_id must fail."""
        with self.assertRaises(Exception):
            self.Profile.create({"name": "No Model", "code": "col_no_model"})

    # ── §8.1: page_size positive ────────────────────────────────────────────
    def test_page_size_positive_succeeds(self):
        """page_size of 1 (minimum positive integer) is valid."""
        profile = self._profile(code="col_page_size_one", page_size=1)
        self.assertEqual(profile.page_size, 1)

    # ── §8.1: profile with no columns saves ─────────────────────────────────
    def test_profile_without_columns_saves(self):
        """A Profile with no Columns can be persisted (Aggregate Root without children)."""
        profile = self._profile(code="col_no_columns_save")
        self.assertFalse(profile.column_ids)
        self.assertTrue(profile.id)

    # ── Column default values ────────────────────────────────────────────────
    def test_column_visible_default_is_true(self):
        """Column visible field defaults to True per ORM definition."""
        profile = self._profile(code="col_visible_default")
        col = self.Column.create(
            {"profile_id": profile.id, "field_id": self.partner_email.id}
        )
        self.assertTrue(col.visible)
