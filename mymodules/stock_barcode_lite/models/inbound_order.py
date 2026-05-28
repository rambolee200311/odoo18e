# -*- coding: utf-8 -*-

from odoo import _, api, fields, models
from odoo.http import request
from odoo.exceptions import UserError, ValidationError

class InboundOrder(models.Model):
    _inherit = "world.depot.inbound.order"

    creation_source = fields.Selection([("manual", "Manual"), ("api", "API"), ("import", "Import")], string="Creation Source", default="manual", readonly=True, copy=False)



    def action_open_inbound_product_import_wizard(self):
        for rec in self:
            if rec.state != "new":
                raise UserError(_("Only new inbound orders can import products."))
            if rec.inbound_order_product_ids:
                raise UserError(_("This inbound order already has pallet/product lines."))
            return {
                "type": "ir.actions.act_window",
                "name": _("Import Products"),
                "res_model": "inbound.product.import.wizard",
                "view_mode": "form",
                "views": [(False, "form")],
                "target": "new",
                "context": {
                    "default_inbound_order_id": rec.id,
                },
            }
        return False


class InboundOrderProduct(models.Model):
    _inherit = "world.depot.inbound.order.product"

    creation_source = fields.Selection([("manual", "Manual"), ("api", "API"), ("import", "Import")], string="Creation Source", default="manual", readonly=True, copy=False)

    @api.constrains("inbound_order_id", "pallet_no")
    def check_pallet_no_unique_by_project(self):
        pallet_model = self.env["world.depot.inbound.order.product"]
        for rec in self:
            if not rec.pallet_no or not rec.inbound_order_id or rec.inbound_order_id.state == "cancel":
                continue
            domain = [
                ("id", "!=", rec.id),
                ("pallet_no", "=", rec.pallet_no),
                ("inbound_order_id.project", "=", rec.inbound_order_id.project.id),
                ("inbound_order_id.state", "!=", "cancel"),
            ]
            existing = pallet_model.sudo().search(domain, limit=1)
            if existing:
                raise ValidationError(
                    _('Pallet No "%s" already exists in inbound order "%s" for this project.')
                    % (rec.pallet_no, existing.inbound_order_id.billno or existing.inbound_order_id.reference)
                )

    def unlink(self):
        for rec in self:
            if rec.inbound_order_product_pallet_ids:
                rec.inbound_order_product_pallet_ids.unlink()
        return super().unlink()


class InboundOrderProductsPallet(models.Model):
    _inherit = "world.depot.inbound.order.products.pallet"

    creation_source = fields.Selection([("manual", "Manual"), ("api", "API"), ("import", "Import")], string="Creation Source", default="manual", readonly=True, copy=False)
