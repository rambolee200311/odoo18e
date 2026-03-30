

import re
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class InboundOrderInherit(models.Model):
    _inherit = "world.depot.inbound.order"

    mrn_id = fields.Many2one("bonded.mrn.master", string="MRN", index=True, copy=False, tracking=True)
    # mrn_code = fields.Char(string="MRN Code", size=18, tracking=True, copy=False, index=True)
    mrn_status = fields.Selection([
        ("pending_declaration", "Pending Declaration"),
        ("declared", "Declared"),
        ("cleared", "Cleared"),
        ("status_changed", "Status Changed"),
        ("exception", "Exception"),
    ], string="MRN Status", default="pending_declaration", tracking=True, copy=False, index=True)

    t1_document_number = fields.Char(string="T1 Document Number", index=True, copy=False)
    t1_status = fields.Selection([
        ("open", "Open"),
        ("closed", "Closed"),
    ], string="T1 Status", default="open", tracking=True, index=True)

    t1_closed_date = fields.Date(string="T1 Closed Date", tracking=True)

    def actionGetMrnMirrorVals(self, mrn):
        return {
            "mrn_status": mrn.mrn_status or False,
            "t1_document_number": mrn.t1_document_number or False,
            "t1_status": mrn.t1_status or "open",
            "t1_closed_date": mrn.t1_closed_date or False,
        }
    @api.onchange("mrn_id")
    def onchangeMrnId(self):
        for rec in self:
            if rec.mrn_id:
                vals = rec.actionGetMrnMirrorVals(rec.mrn_id)
                rec.mrn_status = vals["mrn_status"]
                rec.t1_document_number = vals["t1_document_number"]
                rec.t1_status = vals["t1_status"]
                rec.t1_closed_date = vals["t1_closed_date"]

    @api.onchange("t1_status")
    def onchangeT1Status(self):
        for rec in self:
            rec.t1_closed_date = fields.Date.context_today(rec) if rec.t1_status == "closed" else False


    #改产品海关状态
    def getCustomsStatusByBonded(self, is_bonded):
        return "bonded" if is_bonded else "vrij"

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

    def actionApplyBondedCustomsMrnMappingOnConfirm(self):
        for rec in self:
            customs_status = rec.getCustomsStatusByBonded(rec.is_bonded)
            target_mrn_status = (
                "declared"
                if rec.is_bonded and rec.t1_status == "closed"
                else rec.getMrnStatusByCustomsStatus(customs_status)
            )
            if rec.mrn_status != target_mrn_status:
                rec.write({"mrn_status": target_mrn_status})

            product_records = rec.inbound_order_product_ids.mapped(
                "inbound_order_product_pallet_ids.product_id").filtered(lambda x: x)
            for product in product_records:
                if product.customs_status != customs_status:
                    product.write({"customs_status": customs_status})

    def action_confirm(self):
        res = super().action_confirm()
        self.actionApplyBondedCustomsMrnMappingOnConfirm()
        return res
