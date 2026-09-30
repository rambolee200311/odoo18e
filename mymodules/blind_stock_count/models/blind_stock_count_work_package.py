# -*- coding: utf-8 -*-

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


class BlindStockCountWorkPackage(models.Model):
    _name = "blind.stock.count.work.package"
    _inherit = ["mail.thread"]
    _description = "Blind Stock Count Work Package"

    _order = "id desc"

    name = fields.Char(string="Work Package", required=True, readonly=True, copy=False, index=True, default=lambda self: self.env["ir.sequence"].next_by_code("blind.stock.count.work.package") or _("New"), tracking=True)
    date = fields.Datetime(string="Work Package Date", required=True, default=fields.Datetime.now, copy=False, tracking=True)
    category_id = fields.Many2one("product.category", string="Product Category", required=True, copy=False, index=True,tracking=True)
    owner_id = fields.Many2one("res.partner", string="Owner", compute="compute_owner_id", readonly=True)
    state = fields.Selection([("draft", "Draft"), ("in_progress", "In Progress"), ("done", "Done"), ("cancel", "Cancelled")], string="Status", required=True, default="draft", copy=False, index=True, tracking=True)
    location_line_ids = fields.Many2many("stock.location", "blind_stock_count_work_package_location_rel", "work_package_id", "location_id",tracking=True, string="Location Scope", copy=False)
    count_lines = fields.One2many("blind.stock.count", "work_package_id", string="Blind Stock Counts", copy=False)
    note = fields.Text(string="Notes", copy=False)

    @api.constrains("location_line_ids")
    def check_location_scope(self):
        for rec in self:
            if rec.location_line_ids.filtered(lambda location: location.usage != "internal"):
                raise ValidationError(_("Work package locations must be internal locations."))

    @api.depends("category_id")
    def compute_owner_id(self):
        project_model = self.env["project.project"]
        for rec in self:
            project = project_model.sudo().search([("category", "=", rec.category_id.id)], order="id desc", limit=1) if rec.category_id else False
            rec.owner_id = project.owner

    def action_start(self):
        for rec in self:
            if rec.state != "draft":
                raise UserError(_("Only draft work packages can be started."))
            rec.with_context(blind_stock_count_work_package_action=True).write({"state": "in_progress"})
        return True

    def action_done(self):
        count_model = self.env["blind.stock.count"]
        for rec in self:
            if rec.state != "in_progress":
                raise UserError(_("Only in-progress work packages can be completed."))
            if count_model.sudo().search_count([("work_package_id", "=", rec.id), ("state", "!=", "done")]):
                raise UserError(_("Complete every blind stock count before completing the work package."))
            rec.with_context(blind_stock_count_work_package_action=True).write({"state": "done"})
        return True

    def action_cancel(self):
        count_model = self.env["blind.stock.count"]
        for rec in self:
            if rec.state not in ("draft", "in_progress"):
                raise UserError(_("Only draft or in-progress work packages can be cancelled."))
            if count_model.sudo().search_count([("work_package_id", "=", rec.id), ("state", "=", "counting")]):
                raise UserError(_("Complete or cancel active blind stock counts before cancelling the work package."))
            rec.with_context(blind_stock_count_work_package_action=True).write({"state": "cancel"})
        return True

    def write(self, vals):
        for rec in self:
            if rec.state in ("done", "cancel"):
                raise UserError(_("Completed or cancelled work packages cannot be changed."))
            if "state" in vals and vals["state"] != rec.state and not self.env.context.get("blind_stock_count_work_package_action"):
                raise UserError(_("The work package status cannot be changed directly."))
            if rec.state != "draft" and {"category_id", "location_line_ids"}.intersection(vals):
                raise UserError(_("Product category and location scope cannot be changed after the work package starts."))
        return super().write(vals)
