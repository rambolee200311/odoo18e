from odoo import api, fields, models, _


CUSTOMS_STATUS_SELECTION = [
    ("vrij", "Vrij(Free/Non-bonded/Free circulation)"),
    ("rto", "RTO(Return to origin/Return shipment)"),
    ("entrepot", "Entrepot(Bonded warehouse/Warehouse regime)"),
    ("accijns", "Accijns(Excise goods/Excise duty regime)"),
    ("ivv", "IVV(Import, export, transit & equivalent traffic)"),
]
T1_STATUS_SELECTION = [("open", "Open"), ("closed", "Closed")]


class BondedCustomsDocument(models.Model):
    _name = "bonded.customs.document"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _description = "Customs Document"
    _order = "id desc"
    _rec_name = "customs_document_number"

    _sql_constraints = [("customs_document_number_unique", "unique(customs_document_number)",
                         "Customs Document Number must be unique.")]

    customs_document_number = fields.Char(string="Customs Document Number", index=True, tracking=True, copy=False)

    customs_document_type = fields.Selection(
        [("import_declaration", "Import Declaration"),
         ("bonded_warehouse_inbound", "Bonded Warehouse Inbound"),
         ("t1_transit_declaration", "T1 Transit Declaration"),
         ("bonded_to_free_circulation", "Bonded to Free Circulation"),
         ("bonded_to_t1", "Bonded to T1"),
         ("export_declaration", "Export Declaration"),
         ("rto_declaration", "RTO Declaration"),
         ("excise_declaration", "Excise Declaration"),
         ("ivv_declaration", "IVV Declaration"),
         ("equivalent_traffic_declaration", "Equivalent Traffic Declaration")], string="Customs Document Type",
         default="import_declaration", index=True, tracking=True)

    customs_status = fields.Selection(CUSTOMS_STATUS_SELECTION, string="Customs Status", required=True, default="vrij", index=True, tracking=True)
    unique_identifier = fields.Char(string="Unique Identifier", index=True, tracking=True)
    inbound_order_id = fields.Many2one("world.depot.inbound.order", string="Inbound Order", index=True, tracking=True)
    inbound_reference = fields.Char(string="Inbound Reference", index=True, tracking=True)

    t1_document_number = fields.Char(string="T1 Document Number", index=True, tracking=True)
    t1_status = fields.Selection(T1_STATUS_SELECTION, string="T1 Status", required=True, default="open", index=True, tracking=True)
    t1_closed_date = fields.Date(string="T1 Closed Date", tracking=True)
    #active = fields.Boolean(string="Active", default=True, index=True)

    def write(self, vals):
        vals_write = dict(vals)
        if vals_write.get("t1_status") != "closed" and "t1_status" in vals_write:
            vals_write["t1_closed_date"] = False
        res = super().write(vals_write)
        if any(x in vals_write for x in ["customs_status", "t1_document_number", "t1_status", "t1_closed_date"]):
            self.actionSyncLinkedRecordsByDocument()
        return res


    def actionSyncLinkedRecordsByDocument(self):
        inbound_env = self.env["world.depot.inbound.order"]
        outbound_env = self.env["world.depot.outbound.order"]

        for rec in self:
            inbound_ids = inbound_env.sudo().search([("customs_document_id", "=", rec.id)]).ids
            outbound_ids = outbound_env.sudo().search([("customs_document_id", "=", rec.id)]).ids

            if inbound_ids:
                inbound_env.browse(inbound_ids).actionSyncCustomsDocumentMirrorVals()
                inbound_env.browse(inbound_ids).actionSyncCustomsDocumentToInboundPicking()

            if outbound_ids:
                outbound_env.browse(outbound_ids).actionSyncCustomsDocumentMirrorVals()
                outbound_env.browse(outbound_ids).actionSyncCustomsDocumentToOutboundPicking()

        return True


