

import re
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class InboundOrderInherit(models.Model):
    _inherit = "world.depot.inbound.order"


    _sql_constraints = [
        ("mrn_code_unique", "unique(mrn_code)", "MRN Code must be unique."),
    ]

    mrn_code = fields.Char(string="MRN Code", size=18, tracking=True, copy=False, index=True)
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

    @api.onchange("mrn_code")
    def onchangeMrnCodeUpper(self):
        for rec in self:
            rec.mrn_code = (rec.mrn_code or "").strip().upper() or False

    def getMrnRegexPattern(self):
        return r"^[A-Z]{2}[A-Z0-9]{16}$"

    @api.constrains("mrn_code")
    def checkMrnCodeFormat(self):
        pattern = self.getMrnRegexPattern()
        regex = re.compile(pattern)
        for rec in self:
            if rec.mrn_code and not regex.fullmatch((rec.mrn_code or "").strip().upper()):
                raise ValidationError(
                    _("MRN format invalid. It must be 18 chars: 2-letter country code + 16 uppercase alphanumeric chars.")
                )
    #改产品海关状态
    def getCustomsStatusByBonded(self, is_bonded):
        return "bonded" if is_bonded else "vrij"

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

    def actionApplyBondedCustomsMrnMappingOnConfirm(self):
        for rec in self:
            customs_status = rec.getCustomsStatusByBonded(rec.is_bonded)
            mrn_status = rec.getMrnStatusByCustomsStatus(customs_status)
            if rec.mrn_status != mrn_status:
                rec.write({"mrn_status": mrn_status})

            product_records = rec.inbound_order_product_ids.mapped(
                "inbound_order_product_pallet_ids.product_id").filtered(lambda x: x)
            for product in product_records:
                if product.customs_status != customs_status:
                    product.write({"customs_status": customs_status})

    def action_confirm(self):
        res = super().action_confirm()
        self.actionApplyBondedCustomsMrnMappingOnConfirm()
        return res




    @api.constrains("mrn_code")
    def checkMrnCodeUnique(self):
        for rec in self:
            if not rec.mrn_code:
                continue
            existed = self.env["world.depot.inbound.order"].sudo().search(
                [("mrn_code", "=", rec.mrn_code), ("id", "!=", rec.id)],
                limit=1
            )
            if existed:
                raise ValidationError(_("MRN Code must be unique."))