# -*- coding: utf-8 -*-
from odoo import _, api, fields, models


class StatementPeriod(models.Model):
    _name = "statement.period"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _description = "Statement Period"
    _order = "id desc"

    name = fields.Char(string="Statement No", required=True, default=lambda self: _("New"), copy=False, index=True, tracking=True)
    date_start = fields.Date(string="Start Date", required=True, copy=False, index=True)
    date_end = fields.Date(string="End Date", required=True, copy=False, index=True)
    project_id = fields.Many2one("project.project", string="Project", required=True, ondelete="restrict", copy=False, index=True, tracking=True)
    currency_id = fields.Many2one("res.currency", related="project_id.quotation_id.currency_id", string="Currency", store=True, readonly=True, copy=False, index=True)
    state = fields.Selection([("draft", "Draft"), ("expense_confirmed", "Expense Confirmed"), ("payment_in_progress", "Payment In Progress"), ("calculated", "Calculated"), ("cancelled", "Cancelled")], string="State", required=True, default="draft", copy=False, index=True, tracking=True)
    expense_confirmed_datetime = fields.Datetime(string="Expense Confirmed Date", readonly=True, copy=False, index=True)

    def action_confirm_expense(self):
        for rec in self:
            rec.write({"state": "expense_confirmed", "expense_confirmed_datetime": fields.Datetime.now()})

    def action_draft(self):
        for rec in self:
            rec.write({"state": "draft"})

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("name", _("New")) == _("New"):
                vals["name"] = self.env["ir.sequence"].next_by_code("statement.period") or _("New")
        return super().create(vals_list)
