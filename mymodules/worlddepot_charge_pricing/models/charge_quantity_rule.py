# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class ChargeQuantityRule(models.Model):
    _name = "charge.quantity.rule"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _description = "Charge Quantity Rule"
    _order = "id desc"

    name = fields.Char(string="Rule Name", required=True, index=True)
    code = fields.Char(string="Rule Code", required=True, index=True)

    source_object = fields.Selection(
        [
            ("operation", "Operation Order"),
            ("waybill", "Waybill"),
            ("exchange", "Exchange Extension"),
            ("customs", "Customs Extension"),
        ],
        string="Source Object",
        required=True,
        default="operation",
        index=True,
    )

    source_field = fields.Char(string="Source Field", required=True)
    min_value = fields.Integer(string="Min Value", default=0)
    active = fields.Boolean(string="Active", default=True, index=True)
    remark = fields.Text(string="Remark")

    _sql_constraints = [
        ("uniq_rule_code", "unique(code)", "Rule Code must be unique."),
    ]

    @api.constrains("min_value")
    def check_min_value(self):
        for rec in self:
            if rec.min_value < 0:
                raise ValidationError(_("Min Value must be >= 0."))
