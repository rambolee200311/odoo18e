# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class ChargeRule(models.Model):
    _name = "charge.rule"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _description = "Charge Rule"
    _order = "id desc"

    name = fields.Char(string="Rule Name", required=True, index=True)
    rule_type = fields.Selection(
        [
            ("base", "Base"),
            ("step", "Step"),
            ("condition", "Condition"),
            ("trigger", "Trigger"),
            ("duration", "Duration"),
            ("at_cost", "At Cost"),
        ],
        string="Rule Type",
        required=True,
        default="base",
        index=True,
    )

    currency_id = fields.Many2one(
        "res.currency",
        string="Currency",
        required=True,
        default=lambda self: self.env.company.currency_id.id,
        options="{'no_create': True, 'no_open': True}",
    )
    base_rate = fields.Monetary(string="Base Rate", currency_field="currency_id", default=0.0)

    # 复杂规则参数：阶梯/时长封顶/条件配置等
    rule_config = fields.Text(string="Rule Config", tracking=True)

    condition_expr = fields.Text(string="Condition Expression")
    trigger_event = fields.Selection(
        [
            ("state_change", "State Change"),
            ("external_notify", "External Notify"),
        ],
        string="Trigger Event",
        index=True,
    )

    effective_from = fields.Date(string="Effective From", required=True, index=True, default=fields.Date.context_today)
    effective_to = fields.Date(string="Effective To", index=True)
    active = fields.Boolean(string="Active", default=True, index=True)
    remark = fields.Text(string="Remark")

    @api.constrains("effective_from", "effective_to")
    def check_effective_date(self):
        for rec in self:
            if rec.effective_to and rec.effective_from and rec.effective_to < rec.effective_from:
                raise ValidationError(_("Effective To must be >= Effective From."))
