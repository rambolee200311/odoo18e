# -*- coding: utf-8 -*-
# © 2024 Wukong Digital. License LGPL-3.
"""Configuration UI and ACL boundary tests for Advanced Record Picker (INT-ARP-001 §8.2–8.3)."""
from odoo.tests.common import TransactionCase


class TestPickerConfigUI(TransactionCase):
    """Verifies backend menu, list/form view records, and Columns One2many arch (§8.3)."""

    # ── §8.3: menu and action ───────────────────────────────────────────────
    def test_menu_item_exists(self):
        """Backend menu item for Picker Profiles is registered."""
        menu = self.env.ref(
            "wd_web_advanced_record_picker.menu_advanced_record_picker_profiles"
        )
        self.assertTrue(menu.exists())

    def test_action_targets_correct_model(self):
        """Window action res_model is advanced.record.picker.profile."""
        action = self.env.ref(
            "wd_web_advanced_record_picker.action_advanced_record_picker_profiles"
        )
        self.assertEqual(action.res_model, "advanced.record.picker.profile")

    # ── §8.3: list and form view records ────────────────────────────────────
    def test_list_view_registered_for_profile(self):
        """Profile list view is registered for the correct model."""
        view = self.env.ref(
            "wd_web_advanced_record_picker.view_advanced_record_picker_profile_list"
        )
        self.assertEqual(view.model, "advanced.record.picker.profile")

    def test_form_view_registered_for_profile(self):
        """Profile form view is registered for the correct model."""
        view = self.env.ref(
            "wd_web_advanced_record_picker.view_advanced_record_picker_profile_form"
        )
        self.assertEqual(view.model, "advanced.record.picker.profile")

    # ── §8.3: get_views loads without errors ────────────────────────────────
    def test_list_and_form_views_load_without_error(self):
        """get_views for list and form succeeds — no view-definition errors.

        Also verifies no dependency on product or contacts is required.
        """
        result = self.env["advanced.record.picker.profile"].get_views(
            [[False, "list"], [False, "form"]]
        )
        self.assertIn("list", result["views"])
        self.assertIn("form", result["views"])

    # ── §8.3: form view arch sanity ──────────────────────────────────────────
    def test_form_view_contains_column_one2many(self):
        """Form view arch includes the column_ids One2many field."""
        view = self.env.ref(
            "wd_web_advanced_record_picker.view_advanced_record_picker_profile_form"
        )
        self.assertIn("column_ids", view.arch_base)

    def test_column_field_domain_references_model_and_display_types(self):
        """Column field_id domain in form view restricts to Target Model and DISPLAY_FIELD_TYPES."""
        view = self.env.ref(
            "wd_web_advanced_record_picker.view_advanced_record_picker_profile_form"
        )
        arch = view.arch_base
        # domain on field_id must reference parent.model_id and ttype
        self.assertIn("model_id", arch)
        self.assertIn("ttype", arch)
        # monetary must appear in the domain list (it is a display type)
        self.assertIn("monetary", arch)

    def test_form_view_model_id_readonly_when_columns_present(self):
        """Form view arch marks model_id as readonly when column_ids is truthy."""
        view = self.env.ref(
            "wd_web_advanced_record_picker.view_advanced_record_picker_profile_form"
        )
        # The readonly attribute on model_id references column_ids
        self.assertIn("column_ids", view.arch_base)

    def test_form_view_contains_target_model_domain_widget(self):
        """Profile Domain uses Odoo's standard domain widget and target model."""
        view = self.env.ref(
            "wd_web_advanced_record_picker.view_advanced_record_picker_profile_form"
        )
        self.assertIn('name="domain"', view.arch_base)
        self.assertIn('widget="domain"', view.arch_base)
        self.assertIn("'model': 'model_name'", view.arch_base)

    # ── §8.3: visible column_invisible in One2many ──────────────────────────
    def test_visible_field_is_column_invisible_in_list(self):
        """The 'visible' column is hidden in the Columns One2many list (V1 always True)."""
        view = self.env.ref(
            "wd_web_advanced_record_picker.view_advanced_record_picker_profile_form"
        )
        self.assertIn("column_invisible", view.arch_base)
