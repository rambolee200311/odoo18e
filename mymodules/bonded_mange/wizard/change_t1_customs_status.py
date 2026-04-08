from odoo import fields, models, _
from odoo.exceptions import ValidationError
from odoo.addons.bonded_mange.bonded_models.product_product_inherit import CUSTOMS_STATUS_SELECTION


class WorldDepotInboundCustomsWizard(models.TransientModel):
    _name = "world.depot.inbound.customs.wizard"
    _description = "Inbound Customs Status Wizard"
    _order = "id desc"

    inbound_order_id = fields.Many2one("world.depot.inbound.order", string="Inbound Order", required=True, index=True, readonly=True)
    customs_status = fields.Selection(CUSTOMS_STATUS_SELECTION, string="Customs Status", required=True, index=True)

    def actionApplyInboundCustoms(self):
        for rec in self:
            rec.inbound_order_id.write({
                "customs_status": rec.customs_status or False,
                "customs_status_manual": True,
            })
            rec.inbound_order_id.actionSyncInboundSnapshotToMrn()
            rec.inbound_order_id.actionSyncInboundT1ToMrnAndQuant()
        return {"type": "ir.actions.act_window_close"}


class WorldDepotInboundT1Wizard(models.TransientModel):
    _name = "world.depot.inbound.t1.wizard"
    _description = "Inbound T1 Wizard"
    _order = "id desc"

    inbound_order_id = fields.Many2one("world.depot.inbound.order", string="Inbound Order", required=True, index=True, readonly=True)
    t1_document_number = fields.Char(string="T1 Document Number")
    t1_status = fields.Selection([("open", "Open"), ("closed", "Closed")], string="T1 Status", required=True, default="open", index=True)
    t1_closed_date = fields.Date(string="T1 Closed Date")

    def actionApplyInboundT1(self):
        for rec in self:
            vals = {
                "t1_document_number": rec.t1_document_number or False,
                "t1_status": rec.t1_status,
                "t1_closed_date": rec.t1_closed_date or False,
            }
            if rec.t1_status == "closed" and not vals["t1_closed_date"]:
                vals["t1_closed_date"] = fields.Date.context_today(rec)
            if rec.t1_status != "closed":
                vals["t1_closed_date"] = False
            rec.inbound_order_id.write(vals)
            rec.inbound_order_id.actionSyncInboundSnapshotToMrn()
            rec.inbound_order_id.actionSyncInboundT1ToMrnAndQuant()
        return {"type": "ir.actions.act_window_close"}