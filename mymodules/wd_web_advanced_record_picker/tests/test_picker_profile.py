# -*- coding: utf-8 -*-
from odoo import Command
from odoo.exceptions import AccessError, ValidationError
from odoo.tests.common import TransactionCase, new_test_user
from psycopg2 import IntegrityError


class TestPickerProfile(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Profile = cls.env["advanced.record.picker.profile"]
        cls.Column = cls.env["advanced.record.picker.column"]
        cls.partner_model = cls.env["ir.model"]._get("res.partner")
        cls.user_model = cls.env["ir.model"]._get("res.users")
        cls.partner_name = cls.env["ir.model.fields"]._get("res.partner", "name")
        cls.partner_email = cls.env["ir.model.fields"]._get("res.partner", "email")
        cls.partner_image = cls.env["ir.model.fields"]._get("res.partner", "image_1920")
        cls.user_login = cls.env["ir.model.fields"]._get("res.users", "login")

    def _profile(self, **values):
        defaults = {
            "name": "Partner Picker",
            "code": "partner_picker",
            "model_id": self.partner_model.id,
        }
        defaults.update(values)
        return self.Profile.create(defaults)

    def test_profile_basics_and_code_normalization(self):
        profile = self._profile(code="  partner_picker_trimmed  ")
        self.assertEqual(profile.code, "partner_picker_trimmed")
        self.assertTrue(self._profile(code="partner_picker_empty_columns"))

        with self.assertRaises(ValidationError):
            self._profile(code="   ")
        with self.cr.savepoint(), self.assertRaises(IntegrityError):
            self._profile(code="partner_picker_trimmed")
        with self.assertRaises(ValidationError):
            self._profile(page_size=0)
        with self.assertRaises(ValidationError):
            self._profile(page_size=-1)

    def test_columns_constraints_and_model_change_guard(self):
        profile = self._profile(
            column_ids=[
                Command.create(
                    {
                        "field_id": self.partner_name.id,
                        "filterable": True,
                    }
                )
            ]
        )
        self.assertEqual(profile.column_ids.field_id, self.partner_name)

        with self.assertRaises(ValidationError):
            profile.write({"model_id": self.user_model.id})

        with self.cr.savepoint(), self.assertRaises(IntegrityError):
            self.Column.create(
                {
                    "profile_id": profile.id,
                    "field_id": self.partner_name.id,
                }
            )
        with self.assertRaises(ValidationError):
            self.Column.create(
                {
                    "profile_id": profile.id,
                    "field_id": self.user_login.id,
                }
            )
        with self.assertRaises(ValidationError):
            self.Column.create(
                {
                    "profile_id": profile.id,
                    "field_id": self.partner_image.id,
                }
            )
        with self.assertRaises(ValidationError):
            self.Column.create(
                {
                    "profile_id": profile.id,
                    "field_id": self.partner_email.id,
                    "visible": False,
                }
            )

    def test_filterable_monetary_field_is_rejected(self):
        monetary_field = self.env["ir.model.fields"].search(
            [
                ("model", "=", "res.partner"),
                ("ttype", "=", "monetary"),
            ],
            limit=1,
        )
        if monetary_field:
            profile = self._profile(code="partner_picker_monetary")
            with self.assertRaises(ValidationError):
                self.Column.create(
                    {
                        "profile_id": profile.id,
                        "field_id": monetary_field.id,
                        "filterable": True,
                    }
                )

    def test_default_order_uses_standard_orm_validation(self):
        self._profile(code="partner_picker_order", default_order="name asc, id desc")
        with self.assertRaises(ValidationError):
            self._profile(
                code="partner_picker_invalid_order",
                default_order="does_not_exist desc",
            )
        with self.assertRaises(ValidationError):
            self._profile(
                code="partner_picker_invalid_order_syntax",
                default_order="name;DROP TABLE res_partner",
            )

    def test_profile_domain_uses_target_model_validation(self):
        profile = self._profile(
            code="partner_picker_domain",
            domain="[('is_company', '=', True)]",
        )
        self.assertEqual(profile.domain, "[('is_company', '=', True)]")

        with self.assertRaises(ValidationError):
            self._profile(
                code="partner_picker_invalid_domain_syntax",
                domain="[('company_type', '=', 'company')",
            )
        with self.assertRaises(ValidationError):
            self._profile(
                code="partner_picker_invalid_domain_field",
                domain="[('field_does_not_exist', '=', True)]",
            )
        with self.assertRaises(ValidationError):
            self._profile(
                code="partner_picker_dynamic_domain",
                domain="[('id', '=', uid)]",
            )

    def test_profile_domain_defaults_to_empty_domain(self):
        self.assertEqual(
            self._profile(code="partner_picker_empty_domain").domain,
            "[]",
        )

    def test_model_can_change_without_columns_and_columns_cascade(self):
        profile = self._profile(code="partner_picker_model_change")
        profile.write({"model_id": self.user_model.id})
        self.assertEqual(profile.model_id, self.user_model)

        profile = self._profile(
            code="partner_picker_cascade",
            column_ids=[
                Command.create({"field_id": self.partner_name.id}),
            ],
        )
        column = profile.column_ids
        profile.unlink()
        self.assertFalse(column.exists())

    def test_configuration_acl(self):
        profile = self._profile(
            code="partner_picker_acl",
            column_ids=[Command.create({"field_id": self.partner_name.id})],
        )
        internal_user = new_test_user(
            self.env,
            login="advanced_record_picker_internal",
            groups="base.group_user",
        )
        profile_user = self.Profile.with_user(internal_user).browse(profile.id)
        column_user = self.Column.with_user(internal_user).browse(profile.column_ids.id)
        self.assertEqual(profile_user.read(["code"])[0]["code"], "partner_picker_acl")
        self.assertTrue(column_user.exists())
        with self.assertRaises(AccessError):
            profile_user.write({"name": "Nope"})
        with self.assertRaises(AccessError):
            profile_user.unlink()
        with self.assertRaises(AccessError):
            self.Profile.with_user(internal_user).create(
                {
                    "name": "Nope",
                    "code": "partner_picker_acl_new",
                    "model_id": self.partner_model.id,
                }
            )
        with self.assertRaises(AccessError):
            column_user.write({"sequence": 20})
        with self.assertRaises(AccessError):
            column_user.unlink()
        with self.assertRaises(AccessError):
            self.Column.with_user(internal_user).create(
                {
                    "profile_id": profile.id,
                    "field_id": self.partner_name.id,
                }
            )
