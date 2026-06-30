from odoo import fields, models, _
from odoo.exceptions import ValidationError
from odoo.addons.bonded_mange.bonded_models.product_product_inherit import CUSTOMS_STATUS_SELECTION


class StockMoveLineBulkCustomsWizard(models.TransientModel):
    _name = "stock.move.line.bulk.customs.wizard"
    _description = "Stock Move Line Bulk Customs Wizard"
    _order = "id desc"

    query_type = fields.Selection([("mrn", "MRN"), ("unique_identifier", "Unique Identifier")], string="Query Type", required=True, default="mrn", index=True)
    mrn_id = fields.Many2one("bonded.mrn.master", string="MRN", index=True)
    unique_identifier = fields.Char(string="Unique Identifier", index=True)
    candidate_inbound_ids = fields.Many2many("world.depot.inbound.order", string="Candidate Inbound", copy=False)
    target_inbound_id = fields.Many2one("world.depot.inbound.order", string="Selected Inbound", domain="[('id', 'in', candidate_inbound_ids)]", index=True)
    preview_line_ids = fields.One2many("stock.move.line.bulk.customs.preview.line", "wizard_id", string="Search Result", copy=False)
    customs_status = fields.Selection(CUSTOMS_STATUS_SELECTION, string="Customs Status", required=True, index=True)
    change_reason = fields.Char(string="Change Reason")

    def actionBuildInboundDomain(self):
        self.ensure_one()
        if self.query_type == "mrn":
            if not self.mrn_id:
                raise ValidationError(_("Please select MRN."))
            return [("mrn_id", "=", self.mrn_id.id)]
        if not (self.unique_identifier or "").strip():
            raise ValidationError(_("Please input Unique Identifier."))
        return [("unique_identifier", "=", self.unique_identifier.strip())]

    def actionSearchInbound(self):
        inbound_model = self.env["world.depot.inbound.order"]
        for rec in self:
            domain = rec.actionBuildInboundDomain()
            inbound_ids = inbound_model.sudo().search(domain, order="id desc").ids
            rec.candidate_inbound_ids = [(6, 0, inbound_ids)]
            command_list = [(5, 0, 0)]
            for inbound_id in inbound_ids:
                command_list.append((0, 0, {"inbound_id": inbound_id}))
            rec.preview_line_ids = command_list
            if rec.target_inbound_id and rec.target_inbound_id.id not in inbound_ids:
                rec.target_inbound_id = False
            if len(inbound_ids) == 1:
                rec.target_inbound_id = inbound_ids[0]

    def actionGetTargetInbound(self):
        self.ensure_one()
        if not self.candidate_inbound_ids:
            self.actionSearchInbound()
        if not self.target_inbound_id:
            raise ValidationError(_("Please select one inbound from search result."))
        if self.target_inbound_id.id not in self.candidate_inbound_ids.ids:
            raise ValidationError(_("Selected inbound is not in current search result."))
        return self.target_inbound_id

    def actionApplyBulkCustoms(self):
        for rec in self:
            inbound = rec.actionGetTargetInbound()
            vals = {"customs_status": rec.customs_status}
            if "customs_status_manual" in inbound._fields:
                vals["customs_status_manual"] = True
            inbound.write(vals)
            inbound.actionSyncInboundSnapshotToMrn()
            inbound.actionSyncInboundT1ToMrnAndQuant()
        return {"type": "ir.actions.act_window_close"}


class StockMoveLineBulkCustomsPreviewLine(models.TransientModel):
    _name = "stock.move.line.bulk.customs.preview.line"
    _description = "Stock Move Line Bulk Customs Preview Line"
    _order = "id desc"

    wizard_id = fields.Many2one("stock.move.line.bulk.customs.wizard", string="Wizard", required=True, ondelete="cascade", index=True)
    inbound_id = fields.Many2one("world.depot.inbound.order", string="Inbound", required=True, index=True)
    billno = fields.Char(string="Inbound No", related="inbound_id.billno", store=False, readonly=True)
    mrn_id = fields.Many2one("bonded.mrn.master", string="MRN", related="inbound_id.mrn_id", store=False, readonly=True)
    unique_identifier = fields.Char(string="Unique Identifier", related="inbound_id.unique_identifier", store=False, readonly=True)
    state = fields.Selection(related="inbound_id.state", store=False, readonly=True)
    customs_status = fields.Selection(CUSTOMS_STATUS_SELECTION, string="Customs Status", related="inbound_id.customs_status", store=False, readonly=True)


class StockMoveLineBulkT1Wizard(models.TransientModel):
    _name = "stock.move.line.bulk.t1.wizard"
    _description = "Stock Move Line Bulk T1 Wizard"
    _order = "id desc"

    query_type = fields.Selection([("mrn", "MRN"), ("unique_identifier", "Unique Identifier")], string="Query Type", required=True, default="mrn", index=True)
    mrn_id = fields.Many2one("bonded.mrn.master", string="MRN", index=True)
    unique_identifier = fields.Char(string="Unique Identifier", index=True)
    candidate_inbound_ids = fields.Many2many("world.depot.inbound.order", string="Candidate Inbound", copy=False)
    target_inbound_id = fields.Many2one("world.depot.inbound.order", string="Selected Inbound", domain="[('id', 'in', candidate_inbound_ids)]", index=True)
    preview_line_ids = fields.One2many("stock.move.line.bulk.t1.preview.line", "wizard_id", string="Search Result", copy=False)
    t1_document_number = fields.Char(string="T1 Document Number")
    t1_status = fields.Selection([("open", "Open"), ("closed", "Closed")], string="T1 Status", required=True, default="open", index=True)
    t1_closed_date = fields.Date(string="T1 Closed Date")

    def actionBuildInboundDomain(self):
        self.ensure_one()
        if self.query_type == "mrn":
            if not self.mrn_id:
                raise ValidationError(_("Please select MRN."))
            return [("mrn_id", "=", self.mrn_id.id)]
        if not (self.unique_identifier or "").strip():
            raise ValidationError(_("Please input Unique Identifier."))
        return [("unique_identifier", "=", self.unique_identifier.strip())]

    def actionSearchInbound(self):
        inbound_model = self.env["world.depot.inbound.order"]
        for rec in self:
            domain = rec.actionBuildInboundDomain()
            inbound_ids = inbound_model.sudo().search(domain, order="id desc").ids
            rec.candidate_inbound_ids = [(6, 0, inbound_ids)]
            command_list = [(5, 0, 0)]
            for inbound_id in inbound_ids:
                command_list.append((0, 0, {"inbound_id": inbound_id}))
            rec.preview_line_ids = command_list
            if rec.target_inbound_id and rec.target_inbound_id.id not in inbound_ids:
                rec.target_inbound_id = False
            if len(inbound_ids) == 1:
                rec.target_inbound_id = inbound_ids[0]

    def actionGetTargetInbound(self):
        self.ensure_one()
        if not self.candidate_inbound_ids:
            self.actionSearchInbound()
        if not self.target_inbound_id:
            raise ValidationError(_("Please select one inbound from search result."))
        if self.target_inbound_id.id not in self.candidate_inbound_ids.ids:
            raise ValidationError(_("Selected inbound is not in current search result."))
        return self.target_inbound_id

    def actionApplyBulkT1(self):
        for rec in self:
            inbound = rec.actionGetTargetInbound()
            t1_closed_date = rec.t1_closed_date or False
            if rec.t1_status == "closed" and not t1_closed_date:
                t1_closed_date = fields.Date.context_today(rec)
            if rec.t1_status != "closed":
                t1_closed_date = False
            vals = {"t1_document_number": rec.t1_document_number or False, "t1_status": rec.t1_status, "t1_closed_date": t1_closed_date}
            if "t1_manual" in inbound._fields:
                vals["t1_manual"] = True
            inbound.write(vals)
            inbound.actionSyncInboundSnapshotToMrn()
            inbound.actionSyncInboundT1ToMrnAndQuant()
        return {"type": "ir.actions.act_window_close"}


class StockMoveLineBulkT1PreviewLine(models.TransientModel):
    _name = "stock.move.line.bulk.t1.preview.line"
    _description = "Stock Move Line Bulk T1 Preview Line"
    _order = "id desc"

    wizard_id = fields.Many2one("stock.move.line.bulk.t1.wizard", string="Wizard", required=True, ondelete="cascade", index=True)
    inbound_id = fields.Many2one("world.depot.inbound.order", string="Inbound", required=True, index=True)

    mrn_id = fields.Many2one("bonded.mrn.master", string="MRN", related="inbound_id.mrn_id", store=False, readonly=True)
    unique_identifier = fields.Char(string="Unique Identifier", related="inbound_id.unique_identifier", store=False, readonly=True)
    state = fields.Selection(related="inbound_id.state", store=False, readonly=True)
    t1_document_number = fields.Char(string="T1 Document Number", related="inbound_id.t1_document_number", store=False, readonly=True)
    t1_status = fields.Selection([("open", "Open"), ("closed", "Closed")], string="T1 Status", related="inbound_id.t1_status", store=False, readonly=True)
    t1_closed_date = fields.Date(string="T1 Closed Date", related="inbound_id.t1_closed_date", store=False, readonly=True)
