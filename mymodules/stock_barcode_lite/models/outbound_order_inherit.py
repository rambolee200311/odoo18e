from odoo import _, api, fields, models
from odoo.http import request
from odoo.exceptions import UserError, ValidationError

class OutboundOrderInherit(models.Model):
    _inherit = "world.depot.outbound.order"

    creation_source = fields.Selection([("manual", "Manual"), ("api", "API"), ("import", "Import")], string="Creation Source", default="manual", readonly=True, copy=False)


    def action_open_outbound_product_import_wizard(self):
        for rec in self:
            if rec.state != "new":
                raise UserError(_("Only new outbound orders can import products."))
            if rec.outbound_order_product_ids:
                raise UserError(_("This outbound order already has pallet/product lines."))
            return {
                "type": "ir.actions.act_window",
                "name": _("Import Products"),
                "res_model": "chenyang.chemical.outbound.product.import.wizard",
                "view_mode": "form",
                "views": [(False, "form")],
                "target": "new",
                "context": {
                    "default_outbound_order_id": rec.id,
                    "default_reference": rec.reference,
                },
            }
        return False

class InboundOrderProduct(models.Model):
    _inherit = "world.depot.outbound.order.product"

    creation_source = fields.Selection([("manual", "Manual"), ("api", "API"), ("import", "Import")],
                                       string="Creation Source", default="manual", readonly=True, copy=False)

    @api.constrains("outbound_order_id", "pallet_no")
    def check_pallet_no_unique_by_project(self):
        pallet_model = self.env["world.depot.outbound.order.product"]
        for rec in self:
            if not rec.pallet_no or not rec.outbound_order_id or rec.outbound_order_id.state == "cancel":
                continue
            domain = [
                ("id", "!=", rec.id),
                ("pallet_no", "=", rec.pallet_no),
                ("outbound_order_id.project", "=", rec.outbound_order_id.project.id),
                ("outbound_order_id.state", "!=", "cancel"),
            ]
            existing = pallet_model.sudo().search(domain, limit=1)
            if existing:
                raise ValidationError(
                    _('Pallet No "%s" already exists in outbound order "%s" for this project.')
                    % (rec.pallet_no, existing.outbound_order_id.billno or existing.outbound_order_id.reference)
                )