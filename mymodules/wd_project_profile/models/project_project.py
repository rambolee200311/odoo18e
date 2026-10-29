# -*- coding: utf-8 -*-

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class ProjectProject(models.Model):
    _inherit = "project.project"

    category = fields.Many2one("product.category", string="Category", index=True, tracking=True)
    owner = fields.Many2one("res.partner", string="Owner", index=True, tracking=True)
    inbound_cmr_template_file = fields.Binary(string="Template File(Inbound CMR)", help="Upload the Excel template file.")
    inbound_cmr_template_file_name = fields.Char(string="Template File Name(Inbound CMR)", help="The name of the uploaded template file.")
    outbound_cmr_template_file = fields.Binary(string="Template File(Outbound CMR)", help="Upload the Excel template file.")
    outbound_cmr_template_file_name = fields.Char(string="Template File Name(Outbound CMR)", help="The name of the uploaded template file.")
    charge_of_pallet = fields.Boolean(string="Charge of Pallet", default=True, tracking=True, help="Whether to charge for pallets.")
    is_check_origin_doc = fields.Boolean(string="Check Origin Doc", default=True, tracking=True, help="Whether to check the origin document.")
    warehouse = fields.Many2one("stock.warehouse", string="Warehouse", tracking=True)
    inbound_pick_type = fields.Many2one("stock.picking.type", string="Inbound Picking Type", domain=[("code", "=", "incoming")], tracking=True)
    outbound_pick_type = fields.Many2one("stock.picking.type", string="Outbound Picking Type", domain=[("code", "in", ["outgoing", "internal"])], tracking=True)
    package_generation_mode = fields.Selection([("inbound", "Inbound"), ("picking", "Picking"), ("none", "No Package")], string="Package Generation Mode", default="picking", required=True, copy=False, index=True)
    pallet_structure_mode = fields.Selection([("known", "Known Pallet Structure"), ("unknown", "Unknown Pallet Structure")], string="Pallet Structure Mode", default="known", required=True, copy=False, index=True)
    stock_report_date_mode = fields.Selection([("validation", "Picking Validation Time"), ("business", "Order Business Date")], string="Inbound Date Management Mode", default="business", required=True, copy=False, index=True)
    barcode_scan_mode = fields.Selection([("native", "Native Barcode"), ("custom", "Custom Barcode Lite")], string="Barcode Scan Mode", default="native", required=True, copy=False, index=True, tracking=True)
    allowed_user_ids = fields.Many2many("res.users", "project_allowed_user_rel", "project_id", "user_id", string="Allowed Users")

    @api.constrains("pallet_structure_mode", "package_generation_mode")
    def check_unknown_pallet_structure_package_generation_mode(self):
        for rec in self:
            if rec.pallet_structure_mode == "unknown" and rec.package_generation_mode != "inbound":
                raise ValidationError(_("Unknown Pallet Structure requires Package Generation Mode to be Inbound."))
