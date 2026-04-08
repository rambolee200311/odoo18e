

import re
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError
from odoo.addons.bonded_mange.bonded_models.product_product_inherit import CUSTOMS_STATUS_SELECTION

class InboundOrderInherit(models.Model):
    _inherit = "world.depot.inbound.order"

    mrn_id = fields.Many2one("bonded.mrn.master", string="MRN", index=True, copy=False, tracking=True,
                             domain="[('id', 'not in', used_mrn_ids)]")
    used_mrn_ids = fields.Many2many(
        "bonded.mrn.master",
        compute="_compute_used_mrn_ids"
    )
    # mrn_code = fields.Char(string="MRN Code", size=18, tracking=True, copy=False, index=True)
    mrn_status = fields.Selection([
        ("pending_declaration", "Pending Declaration"),
        ("declared", "Declared"),
        ("cleared", "Cleared"),
        ("status_changed", "Status Changed"),
        ("exception", "Exception"),
    ], string="MRN Status", default="pending_declaration", tracking=True, copy=False, index=True)

    customs_status = fields.Selection(CUSTOMS_STATUS_SELECTION, string="Customs Status", tracking=True,index=True)
    customs_status_manual = fields.Boolean(string="Customs Status Manual", default=False, tracking=True, index=True,copy=False)

    @api.onchange("is_bonded")
    def onchangeIsBondedSetCustomsStatus(self):
        for rec in self:
            if not rec.customs_status_manual:
                rec.customs_status = "vrij" if rec.is_bonded else False


    t1_document_number = fields.Char(string="T1 Document Number", index=True, copy=False,tracking= True)
    t1_status = fields.Selection([
        ("open", "Open"),
        ("closed", "Closed"),
    ], string="T1 Status", default="open", tracking=True, index=True)

    t1_closed_date = fields.Date(string="T1 Closed Date", tracking=True)

    @api.depends("mrn_id", "state")
    def _compute_used_mrn_ids(self):
        env = self.env
        inbound_model = env["world.depot.inbound.order"]
        used = inbound_model.sudo().search([("mrn_id", "!=", False)]).mapped("mrn_id").ids
        for rec in self:
            rec.used_mrn_ids = [(6, 0, used)]



    def getMrnStatusByCustomsStatus(self, customs_status):
        if customs_status in ("entrepot"):
            return "pending_declaration"
        if customs_status in ("vrij"):
            return "cleared"
        if customs_status in ("rto", "ivv"):
            return "declared"
        if customs_status == "accijns":
            return "exception"
        return "status_changed"

    def actionApplyBondedCustomsMrnMappingOnConfirm(self):
        for rec in self:
            customs_status = rec.customs_status if rec.customs_status is not False else ("vrij" if rec.is_bonded else False)
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

    def actionSyncInboundSnapshotToMrn(self):
        for rec in self:

            vals = {
                "customs_status":  rec.customs_status,
                "mrn_status": rec.mrn_status or False,
                "t1_document_number": rec.t1_document_number or False,
                "t1_status": rec.t1_status or "open",
                "t1_closed_date": rec.t1_closed_date or False,
                "bonded_flag": "true" if rec.is_bonded else "false",
            }
            rec.mrn_id.write(vals)

    def action_confirm(self):
        for rec in self:
            if rec.is_bonded and not rec.mrn_id:
                raise ValidationError(_("Please select MRN"))
            # if rec.is_bonded and rec.t1_status != "closed":
            #     raise ValidationError(_("Please close T1"))
        self.actionApplyBondedCustomsMrnMappingOnConfirm()
        res = super().action_confirm()
        self.actionSyncInboundSnapshotToMrn()
        return res
