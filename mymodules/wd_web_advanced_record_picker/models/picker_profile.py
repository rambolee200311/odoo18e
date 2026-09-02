# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.osv import expression
from odoo.tools.safe_eval import const_eval


class PickerProfile(models.Model):
    _name = "advanced.record.picker.profile"
    _description = "Advanced Record Picker Profile"
    _order = "name, id"

    name = fields.Char(string="Name", required=True)
    code = fields.Char(string="Code", required=True, index=True)
    model_id = fields.Many2one(
        "ir.model",
        string="Target Model",
        required=True,
        ondelete="cascade",
    )
    model_name = fields.Char(related="model_id.model")
    domain = fields.Char(string="Domain", required=True, default="[]")
    active = fields.Boolean(string="Active", default=True)
    default_order = fields.Char(string="Default Order")
    page_size = fields.Integer(string="Page Size", required=True, default=80)
    description = fields.Text(string="Description")
    column_ids = fields.One2many(
        "advanced.record.picker.column",
        "profile_id",
        string="Columns",
        copy=True,
    )

    _sql_constraints = [
        (
            "code_uniq",
            "unique(code)",
            "The Picker Profile code must be unique.",
        ),
    ]

    @api.model_create_multi
    def create(self, vals_list):
        vals_list = [dict(vals) for vals in vals_list]
        for vals in vals_list:
            if isinstance(vals.get("code"), str):
                vals["code"] = vals["code"].strip()
        return super().create(vals_list)

    def write(self, vals):
        vals = dict(vals)
        if isinstance(vals.get("code"), str):
            vals["code"] = vals["code"].strip()

        if "model_id" in vals:
            new_model_id = vals["model_id"] or False
            for profile in self:
                if profile.column_ids and new_model_id != profile.model_id.id:
                    raise ValidationError(
                        _(
                            "The target model cannot be changed while a Picker "
                            "Profile has columns. Remove the columns first."
                        )
                    )
        return super().write(vals)

    @api.constrains("code")
    def _check_code(self):
        for profile in self:
            if not profile.code or not profile.code.strip():
                raise ValidationError(_("The Picker Profile code cannot be empty."))

    @api.constrains("page_size")
    def _check_page_size(self):
        for profile in self:
            if profile.page_size <= 0:
                raise ValidationError(
                    _("The Picker Profile page size must be a positive integer.")
                )

    @api.constrains("default_order", "model_id")
    def _check_default_order(self):
        for profile in self:
            if not profile.default_order or not profile.model_id:
                continue
            target_model = self.env[profile.model_id.model]
            try:
                target_model._order_to_sql(
                    profile.default_order,
                    target_model._where_calc([]),
                )
            except (UserError, ValueError) as error:
                raise ValidationError(
                    _("Invalid default order for %s: %s", profile.model_id.name, error)
                ) from error

    @api.constrains("domain", "model_id")
    def _check_domain(self):
        for profile in self:
            if not profile.model_id:
                continue
            try:
                domain = const_eval(profile.domain or "[]")
                expression.expression(domain, self.env[profile.model_id.model])
            except (
                AssertionError,
                KeyError,
                NameError,
                SyntaxError,
                TypeError,
                ValueError,
            ) as error:
                raise ValidationError(_("Invalid Profile Domain: %s", error)) from error
