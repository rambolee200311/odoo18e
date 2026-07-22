# -*- coding: utf-8 -*-

import base64

from odoo import _, fields, models
from odoo.exceptions import UserError


class InboundProductImportWizard(models.TransientModel):
    _name = "inbound.product.import.wizard"
    _description = "Chenyang Chemical Inbound Product Import Wizard"
    _order = "id desc"

    inbound_order_id = fields.Many2one("world.depot.inbound.order", string="Inbound Order", required=True, readonly=True, index=True, copy=False)
    inbound_project_id = fields.Many2one(related="inbound_order_id.project", string="Project", readonly=True)
    reuse_existing_packages = fields.Boolean(string="Reuse Existing Packages", copy=False)
    reuse_source_inbound_order_line_ids = fields.Many2many("world.depot.inbound.order", string="Reuse Source Inbound Orders", copy=False)
    file = fields.Binary(string="Excel File", required=True, copy=False)
    filename = fields.Char(string="Filename", copy=False)

    def action_import_excel(self):
        for rec in self:
            inbound_order = rec.inbound_order_id
            if inbound_order.state != "new":
                raise UserError(_("Only new inbound orders can import products."))
            if inbound_order.inbound_order_product_ids:
                raise UserError(_("This inbound order already has pallet/product lines."))
            if not rec.file:
                raise UserError(_("Please upload an Excel file."))
            reuse_source_inbound_orders = rec.reuse_source_inbound_order_line_ids.sudo()
            if rec.reuse_existing_packages and not reuse_source_inbound_orders:
                raise UserError(_("Select at least one source inbound order when reusing existing packages."))
            invalid_reuse_source_inbound_orders = reuse_source_inbound_orders.filtered(
                lambda order: order.id == inbound_order.id
                or order.project.id != inbound_order.project.id
                or order.state != "confirm"
            )
            if rec.reuse_existing_packages and invalid_reuse_source_inbound_orders:
                raise UserError(_("Source inbound orders must be confirmed, in the same project, and different from the current inbound order."))

            import_record = rec.env["stock.barcode.lite.sunrise.order.import"].create({
                "name": _("Sunrise Inbound Import - %s") % (inbound_order.billno or inbound_order.reference or inbound_order.id),
                "import_type": "inbound",
                "inbound_order_id": inbound_order.id,
                "reuse_existing_packages": rec.reuse_existing_packages,
                "reuse_source_inbound_order_line_ids": [(6, 0, reuse_source_inbound_orders.ids if rec.reuse_existing_packages else [])],
                "filename": rec.filename,
            })
            import_record.process_import(base64.b64decode(rec.file), rec.filename)
            return {
                "type": "ir.actions.act_window",
                "name": _("Sunrise Order Import"),
                "res_model": "stock.barcode.lite.sunrise.order.import",
                "view_mode": "form",
                "views": [(False, "form")],
                "res_id": import_record.id,
                "target": "current",
            }
        return {"type": "ir.actions.act_window_close"}
