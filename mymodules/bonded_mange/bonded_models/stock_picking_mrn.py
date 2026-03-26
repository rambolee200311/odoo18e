from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError


class StockPicking(models.Model):
    _inherit = "stock.picking"

    def getMrnStatusByCustomsStatus(self, customs_status):
        if customs_status in ("bonded", "entrepot"):
            return "pending_declaration"
        if customs_status in ("vrij", "non_bonded"):
            return "cleared"
        if customs_status in ("rto", "ivv", "ivv_equivalent"):
            return "declared"
        if customs_status == "accijns":
            return "exception"
        return "status_changed"


    def actionSyncInboundCustomsMrnToQuant(self):
        quant_env = self.env["stock.quant"]
        for rec in self:
            if rec.picking_type_code != "incoming" or not rec.inbound_order_id:
                continue
            target_customs_status = "bonded" if rec.inbound_order_id.is_bonded else "vrij"
            target_mrn_status = rec.getMrnStatusByCustomsStatus(target_customs_status)
            target_mrn_code = rec.inbound_order_id.mrn_code

            vals_picking = {}
            if rec.mrn_code != target_mrn_code:
                vals_picking["mrn_code"] = target_mrn_code
            if rec.mrn_status != target_mrn_status:
                vals_picking["mrn_status"] = target_mrn_status
            if vals_picking:
                rec.write(vals_picking)

            for move in rec.move_ids:
                vals_move = {}
                if move.mrn_code != target_mrn_code:
                    vals_move["mrn_code"] = target_mrn_code
                if move.mrn_status != target_mrn_status:
                    vals_move["mrn_status"] = target_mrn_status
                if vals_move:
                    move.write(vals_move)

            for move_line in rec.move_line_ids:
                vals_line = {}
                if move_line.mrn_code != target_mrn_code:
                    vals_line["mrn_code"] = target_mrn_code
                if move_line.mrn_status != target_mrn_status:
                    vals_line["mrn_status"] = target_mrn_status
                if vals_line:
                    move_line.write(vals_line)

            for move_line in rec.move_line_ids.filtered(
                    lambda x: x.location_dest_id.usage in ("internal", "transit") and x.quantity):
                domain = [
                    ("product_id", "=", move_line.product_id.id),
                    ("location_id", "=", move_line.location_dest_id.id),
                    ("lot_id", "=", move_line.lot_id.id or False),
                    ("package_id", "=", move_line.result_package_id.id or False),
                    ("owner_id", "=", move_line.owner_id.id or False),
                ]
                quant_ids = quant_env.sudo().search(domain).ids
                for quant in quant_env.browse(quant_ids):
                    vals_quant = {}
                    if quant.customs_status != target_customs_status:
                        vals_quant["customs_status"] = target_customs_status
                    if quant.mrn_code != target_mrn_code:
                        vals_quant["mrn_code"] = target_mrn_code
                    if quant.mrn_status != target_mrn_status:
                        vals_quant["mrn_status"] = target_mrn_status
                    if vals_quant:
                        quant.write(vals_quant)



    def button_validate(self):

        res = super().button_validate()
        for rec in self:
            if rec.state == "done":
                if rec.inbound_order_id.is_bonded:
                    rec.actionSyncInboundCustomsMrnToQuant()

        return res

    @api.model_create_multi
    def create(self, vals_list):
        inbound_env = self.env["world.depot.inbound.order"]
        picking_env = self.env["stock.picking"]
        for vals in vals_list:
            if vals.get("inbound_order_id"):
                inbound = inbound_env.sudo().browse(vals["inbound_order_id"])
                vals.setdefault("mrn_code", inbound.mrn_code)
                vals.setdefault("mrn_status", inbound.mrn_status)

            if not vals.get("mrn_code") and vals.get("origin"):
                origin_picking = picking_env.sudo().search([("name", "=", vals["origin"])], limit=1)
                if origin_picking:
                    vals.setdefault("mrn_code", origin_picking.mrn_code)
                    vals.setdefault("mrn_status", origin_picking.mrn_status)

        return super().create(vals_list)

    def write(self, vals):
        vals_write = dict(vals)
        if vals_write.get("inbound_order_id"):
            inbound = self.env["world.depot.inbound.order"].sudo().browse(vals_write["inbound_order_id"])
            vals_write.setdefault("mrn_code", inbound.mrn_code)
            vals_write.setdefault("mrn_status", inbound.mrn_status)

        if not vals_write.get("mrn_code") and vals_write.get("origin"):
            origin_picking = self.env["stock.picking"].sudo().search([("name", "=", vals_write["origin"])], limit=1)
            if origin_picking:
                vals_write.setdefault("mrn_code", origin_picking.mrn_code)
                vals_write.setdefault("mrn_status", origin_picking.mrn_status)

        return super().write(vals_write)