from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError


class StockPicking(models.Model):
    _inherit = "stock.picking"

    mrn_id = fields.Many2one("bonded.mrn.master", string="MRN", index=True, copy=False, tracking=True)
    t1_document_number = fields.Char(string="T1 Document Number",store=True, index=True, copy=False)
    t1_status = fields.Selection([
        ("open", "Open"),
        ("closed", "Closed"),
    ], string="T1 Status", default="open",store=True, tracking=True, index=True)

    t1_closed_date = fields.Date(string="T1 Closed Date",store=True, tracking=True)

    @api.depends("mrn_id", "mrn_id.customs_status", "inbound_order_id", "inbound_order_id.is_bonded")
    def _compute_customs_status(self):
        for rec in self:
            if rec.mrn_id and rec.mrn_id.customs_status:
                rec.customs_status = rec.mrn_id.customs_status
            elif rec.inbound_order_id:
                rec.customs_status = "bonded" if rec.inbound_order_id.is_bonded else "vrij"
            else:
                rec.customs_status = False

    def actionGetMrnMirrorVals(self, mrn):
        return {

            "mrn_status": mrn.mrn_status or False,
            "t1_document_number": mrn.t1_document_number or False,
            "t1_status": mrn.t1_status or "open",
            "t1_closed_date": mrn.t1_closed_date or False,
        }


    def getMrnStatusByCustomsStatus(self, customs_status):
        if customs_status in ("bonded", "entrepot"):
            return "pending_declaration"
        if customs_status in ("vrij", "non_bonded"):
            return "cleared"
        if customs_status in ("rto", "ivv"):
            return "declared"
        if customs_status == "accijns":
            return "exception"
        return "status_changed"



    def actionSyncPickingMrnFields(self):
        for rec in self:
            mrn = rec.mrn_id
            if not mrn and rec.outbound_order_id and rec.outbound_order_id.mrn_id:
                mrn = rec.outbound_order_id.mrn_id
            if not mrn and rec.inbound_order_id and rec.inbound_order_id.mrn_id:
                mrn = rec.inbound_order_id.mrn_id
            if not mrn:
                continue

            vals = {}
            if rec.mrn_id != mrn:
                vals["mrn_id"] = mrn.id
            mirror = rec.actionGetMrnMirrorVals(mrn)
            for k, v in mirror.items():
                if rec[k] != v:
                    vals[k] = v
            if vals:
                rec.with_context(skip_mrn_sync=True).write(vals)

            for move in rec.move_ids:
                mv = {}
                if move.mrn_id != rec.mrn_id:
                    mv["mrn_id"] = rec.mrn_id.id
                if move.mrn_status != rec.mrn_status:
                    mv["mrn_status"] = rec.mrn_status
                if move.customs_status != rec.customs_status:
                    mv["customs_status"] = rec.customs_status
                if move.t1_document_number != rec.t1_document_number:
                    mv["t1_document_number"] = rec.t1_document_number
                if move.t1_status != rec.t1_status:
                    mv["t1_status"] = rec.t1_status
                if move.t1_closed_date != rec.t1_closed_date:
                    mv["t1_closed_date"] = rec.t1_closed_date
                if mv:
                    move.write(mv)

            for line in rec.move_line_ids:
                lv = {}
                if line.mrn_id != rec.mrn_id:
                    lv["mrn_id"] = rec.mrn_id.id
                if line.mrn_status != rec.mrn_status:
                    lv["mrn_status"] = rec.mrn_status
                if line.customs_status != rec.customs_status:
                    lv["customs_status"] = rec.customs_status
                if line.t1_document_number != rec.t1_document_number:
                    lv["t1_document_number"] = rec.t1_document_number
                if line.t1_status != rec.t1_status:
                    lv["t1_status"] = rec.t1_status
                if line.t1_closed_date != rec.t1_closed_date:
                    lv["t1_closed_date"] = rec.t1_closed_date
                if lv:
                    line.write(lv)
            quant_env = self.env["stock.quant"]
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
                    if rec.mrn_id and quant.mrn_id != rec.mrn_id:
                        vals_quant["mrn_id"] = rec.mrn_id.id
                    if quant.customs_status != rec.customs_status:
                        vals_quant["customs_status"] = rec.customs_status
                    if quant.mrn_status != rec.mrn_status:
                        vals_quant["mrn_status"] = rec.mrn_status

                    if quant.t1_document_number != rec.t1_document_number:
                        vals_quant["t1_document_number"] = rec.t1_document_number
                    if quant.t1_status != rec.t1_status:
                        vals_quant["t1_status"] = rec.t1_status
                    if quant.t1_closed_date != rec.t1_closed_date:
                        vals_quant["t1_closed_date"] = rec.t1_closed_date
                    if vals_quant:
                        quant.write(vals_quant)

    def button_validate(self):
        for rec in self:

            if rec.picking_type_code == "incoming" and rec.inbound_order_id and rec.inbound_order_id.is_bonded and rec.t1_status != "closed":
                raise ValidationError(_("Bonded goods can only be stored after T1 is closed."))
        res = super().button_validate()
        for rec in self:
            if rec.state == "done" and rec.picking_type_code == "incoming" and rec.inbound_order_id:
                rec.actionSyncPickingMrnFields()
        return res

    @api.model_create_multi
    def create(self, vals_list):
        mrn_model = self.env["bonded.mrn.master"]
        inbound_model = self.env["world.depot.inbound.order"]
        outbound_model = self.env["world.depot.outbound.order"]
        for vals in vals_list:
            if not vals.get("mrn_id") and vals.get("outbound_order_id"):
                outbound = outbound_model.sudo().browse(vals["outbound_order_id"])
                if outbound and outbound.mrn_id:
                    vals["mrn_id"] = outbound.mrn_id.id
            if not vals.get("mrn_id") and vals.get("inbound_order_id"):
                inbound = inbound_model.sudo().browse(vals["inbound_order_id"])
                if inbound and inbound.mrn_id:
                    vals["mrn_id"] = inbound.mrn_id.id
            if vals.get("mrn_id"):
                mrn = mrn_model.sudo().browse(vals["mrn_id"])

                vals.setdefault("mrn_status", mrn.mrn_status)
                vals.setdefault("t1_document_number", mrn.t1_document_number)
                vals.setdefault("t1_status", mrn.t1_status)
                vals.setdefault("t1_closed_date", mrn.t1_closed_date)
        records = super().create(vals_list)
        records.with_context(skip_mrn_master_sync=True).actionSyncPickingMrnFields()
        return records

    def write(self, vals):
        if self.env.context.get("skip_mrn_master_sync"):
            return super().write(vals)
        vals_write = dict(vals)
        mrn_model = self.env["bonded.mrn.master"]
        if "mrn_id" in vals_write and not vals_write["mrn_id"]:
            vals_write.update({

                "mrn_status": False,
                "t1_document_number": False,
                "t1_status": "open",
                "t1_closed_date": False,
            })
        if vals_write.get("mrn_id"):
            mrn = mrn_model.sudo().browse(vals_write["mrn_id"])
            vals_write.setdefault("mrn_status", mrn.mrn_status)
            vals_write.setdefault("t1_document_number", mrn.t1_document_number)
            vals_write.setdefault("t1_status", mrn.t1_status)
            vals_write.setdefault("t1_closed_date", mrn.t1_closed_date)
        res = super().write(vals_write)
        self.with_context(skip_mrn_master_sync=True).actionSyncPickingMrnFields()
        return res