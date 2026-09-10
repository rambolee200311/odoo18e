# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


DISPLAY_FIELD_TYPES = frozenset(
    {
        "char",
        "text",
        "many2one",
        "selection",
        "boolean",
        "integer",
        "float",
        "monetary",
        "date",
        "datetime",
    }
)

FILTER_FIELD_TYPES = frozenset(
    {
        "char",
        "text",
        "many2one",
        "selection",
        "boolean",
        "integer",
        "float",
        "date",
        "datetime",
    }
)


class PickerColumn(models.Model):
    _name = "advanced.record.picker.column"
    _description = "Advanced Record Picker Column"
    _order = "sequence, id"

    profile_id = fields.Many2one(
        "advanced.record.picker.profile",
        string="Picker Profile",
        required=True,
        ondelete="cascade",
        index=True,
    )
    field_id = fields.Many2one(
        "ir.model.fields",
        string="Field",
        required=True,
        ondelete="cascade",
    )
    sequence = fields.Integer(string="Sequence", required=True, default=10)
    visible = fields.Boolean(string="Visible", required=True, default=True)
    filterable = fields.Boolean(string="Filterable", required=True, default=False)

    _sql_constraints = [
        (
            "profile_field_uniq",
            "unique(profile_id, field_id)",
            "A field can only be configured once per Picker Profile.",
        ),
    ]

    @api.constrains("profile_id", "field_id", "visible", "filterable")
    def _check_configuration(self):
        for column in self:
            if not column.profile_id or not column.field_id:
                continue

            if column.field_id.model != column.profile_id.model_id.model:
                raise ValidationError(
                    _(
                        "The column field must belong to the Picker Profile "
                        "target model."
                    )
                )

            field_type = column.field_id.ttype
            if field_type not in DISPLAY_FIELD_TYPES:
                raise ValidationError(
                    _(
                        "The field type %s cannot be used as a Picker display "
                        "column.",
                        field_type,
                    )
                )

            if not column.visible:
                if column.filterable:
                    raise ValidationError(
                        _("A filterable Picker column must also be visible.")
                    )
                raise ValidationError(
                    _("A Picker column cannot be both hidden and non-filterable.")
                )

            if column.filterable and field_type not in FILTER_FIELD_TYPES:
                raise ValidationError(
                    _(
                        "The field type %s cannot be used as a filterable "
                        "Picker column.",
                        field_type,
                    )
                )
