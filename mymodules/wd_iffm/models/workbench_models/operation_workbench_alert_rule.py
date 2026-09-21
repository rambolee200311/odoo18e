from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class OperationWorkbenchAlertRule(models.Model):
    _name = "operation.workbench.alert.rule"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _description = "Operation Workbench Alert Rule"
    _order = "id desc"

    name = fields.Char(string="Rule Name", required=True, default="Default Rule", index=True, copy=False)
    company_id = fields.Many2one("res.company", string="Company", default=lambda self: self.env.company, index=True, copy=False)
    active = fields.Boolean(string="Active", default=True, index=True)
    arrival_near_hours = fields.Integer(string="Arrival Near Hours", required=True, default=72)
    handover_available_days = fields.Integer(string="Handover Available Days", required=True, default=3)
    handover_near_hours = fields.Integer(string="Handover Near Hours", required=True, default=48)
    clearance_available_days = fields.Integer(string="Clearance Available Days", required=True, default=5)
    clearance_near_hours = fields.Integer(string="Clearance Near Hours", required=True, default=48)

    _sql_constraints = [
        ("uniq_operation_workbench_alert_rule_company", "unique(company_id)", "Only one alert rule is allowed per company."),
    ]

    @api.constrains("arrival_near_hours", "handover_available_days", "handover_near_hours", "clearance_available_days", "clearance_near_hours")
    def check_rule_positive_values(self):
        for rec in self:
            if rec.arrival_near_hours <= 0 or rec.handover_available_days <= 0 or rec.handover_near_hours <= 0 or rec.clearance_available_days <= 0 or rec.clearance_near_hours <= 0:
                raise ValidationError(_("All rule values must be greater than zero."))

    @api.model
    def get_rule_values(self, company_id=False):
        env_rule = self.env["operation.workbench.alert.rule"]
        env_company = self.env["res.company"]
        company = env_company.sudo().browse(company_id).exists() if company_id else self.env.company
        rec = env_rule.sudo().search([("company_id", "=", company.id), ("active", "=", True)], order="id desc", limit=1)
        if not rec:
            rec = env_rule.sudo().search([("company_id", "=", False), ("active", "=", True)], order="id desc", limit=1)
        if rec:
            return {
                "arrival_near_hours": rec.arrival_near_hours,
                "handover_available_days": rec.handover_available_days,
                "handover_near_hours": rec.handover_near_hours,
                "clearance_available_days": rec.clearance_available_days,
                "clearance_near_hours": rec.clearance_near_hours,
            }
        return {
            "arrival_near_hours": 72,
            "handover_available_days": 3,
            "handover_near_hours": 48,
            "clearance_available_days": 5,
            "clearance_near_hours": 48,
        }
