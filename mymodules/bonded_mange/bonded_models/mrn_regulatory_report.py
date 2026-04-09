from odoo import api, fields, models, tools, _
from odoo.exceptions import UserError


CUSTOMS_STATUS_SELECTION = [
    ("vrij", "Vrij"),
    ("rto", "Return to Origin"),
    ("entrepot", "Bonded Warehouse"),
    ("accijns", "Excise Goods"),
    ("ivv", "Import/Export/Transit & Equivalent"),
]

MRN_STATUS_SELECTION = [
    ("pending_declaration", "Pending Declaration"),
    ("declared", "Declared"),
    ("cleared", "Cleared"),
    ("status_changed", "Status Changed"),
    ("exception", "Exception"),
]


def build_mrn_detail_action(rec):
    rec.ensure_one()
    if not rec.mrn_id:
        raise UserError(_("MRN is empty."))
    action = rec.env["ir.actions.actions"]._for_xml_id("bonded_mange.action_bonded_mrn_regulatory_report")
    action["name"] = _("MRN Detail: %s") % (rec.mrn_id.code or "")
    action["domain"] = [("mrn_id", "=", rec.mrn_id.id)]
    action["context"] = {"search_default_mrn_id": rec.mrn_id.id}
    return action


class BondedMrnRegulatoryReport(models.Model):
    _name = "bonded.mrn.regulatory.report"
    _description = "MRN Regulatory Report"
    _auto = False
    _order = "id desc"

    record_type = fields.Selection([("flow", "Flow"), ("log", "Log")], string="Record Type", index=True, readonly=True)
    mrn_id = fields.Many2one("bonded.mrn.master", string="MRN", store=True, readonly=True, index=True)
    product_id = fields.Many2one("product.product", string="Product", index=True, readonly=True)
    product_name = fields.Char(string="Product Name", related="product_id.name", readonly=True)
    product_code = fields.Char(string="Product Code", index=True, readonly=True)
    customs_status = fields.Selection(CUSTOMS_STATUS_SELECTION, string="Customs Status", index=True, readonly=True)
    mrn_status = fields.Selection(MRN_STATUS_SELECTION, string="MRN Status", index=True, readonly=True)
    inbound_no = fields.Char(string="Inbound No", index=True, readonly=True)
    outbound_no = fields.Char(string="Outbound No", index=True, readonly=True)
    stock_qty = fields.Float(string="Stock Qty", readonly=True)
    user_id = fields.Many2one("res.users", string="Operator", index=True, readonly=True)
    change_time = fields.Datetime(string="Change Time", index=True, readonly=True)
    remark = fields.Char(string="Remark", readonly=True)
    source_model = fields.Char(string="Source Model", index=True, readonly=True)
    source_res_id = fields.Integer(string="Source Record ID", index=True, readonly=True)
    t1_document_number = fields.Char(string="T1 Document Number", index=True, readonly=True)
    t1_status = fields.Selection([("open", "Open"), ("closed", "Closed")], string="T1 Status", index=True, readonly=True)
    t1_closed_date = fields.Date(string="T1 Closed Date", index=True, readonly=True)

    def action_open_source(self):
        self.ensure_one()
        if not self.source_model or not self.source_res_id:
            raise UserError(_("No source record to open."))
        return {"type": "ir.actions.act_window", "res_model": self.source_model, "res_id": self.source_res_id, "view_mode": "form", "target": "current"}

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute(f"""
            CREATE OR REPLACE VIEW {self._table} AS (
                WITH ledger_summary AS (
                    SELECT l.mrn_id, l.product_id, SUM(l.qty_on_hand) AS stock_qty
                    FROM bonded_identifier_stock_ledger l
                    WHERE l.mrn_id IS NOT NULL
                    GROUP BY l.mrn_id, l.product_id
                ),
                ledger_total AS (
                    SELECT l.mrn_id, SUM(l.qty_on_hand) AS stock_qty
                    FROM bonded_identifier_stock_ledger l
                    WHERE l.mrn_id IS NOT NULL
                    GROUP BY l.mrn_id
                )
                SELECT
                    sml.id AS id,
                    'flow'::varchar AS record_type,
                    COALESCE(sml.mrn_id, sp.mrn_id, io.mrn_id, oo.mrn_id) AS mrn_id,
                    sml.product_id AS product_id,
                    pp.default_code AS product_code,
                    COALESCE(sml.customs_status, pp.customs_status) AS customs_status,
                    COALESCE(sml.mrn_status, sp.mrn_status, io.mrn_status, oo.mrn_status) AS mrn_status,
                    io.billno AS inbound_no,
                    oo.billno AS outbound_no,
                    COALESCE(ls.stock_qty, 0.0) AS stock_qty,
                    COALESCE(sml.create_uid, sp.create_uid) AS user_id,
                    COALESCE(sml.date, sp.date_done, sp.create_date) AS change_time,
                    COALESCE(sp.origin, sml.reference, '') AS remark,
                    'stock.move.line'::varchar AS source_model,
                    sml.id AS source_res_id,
                    COALESCE(sp.t1_document_number, io.t1_document_number, oo.t1_document_number) AS t1_document_number,
                    COALESCE(sp.t1_status, io.t1_status, oo.t1_status) AS t1_status,
                    COALESCE(sp.t1_closed_date, io.t1_closed_date, oo.t1_closed_date) AS t1_closed_date
                FROM stock_move_line sml
                LEFT JOIN stock_picking sp ON sp.id = sml.picking_id
                LEFT JOIN world_depot_inbound_order io ON io.id = sp.inbound_order_id
                LEFT JOIN world_depot_outbound_order oo ON oo.id = sp.outbound_order_id
                LEFT JOIN product_product pp ON pp.id = sml.product_id
                LEFT JOIN ledger_summary ls ON ls.mrn_id = COALESCE(sml.mrn_id, sp.mrn_id, io.mrn_id, oo.mrn_id) AND ls.product_id = sml.product_id
                WHERE COALESCE(sml.mrn_id, sp.mrn_id, io.mrn_id, oo.mrn_id) IS NOT NULL

                UNION ALL

                SELECT
                    -log.id AS id,
                    'log'::varchar AS record_type,
                    COALESCE(log.mrn_id, sp.mrn_id, io.mrn_id, oo.mrn_id) AS mrn_id,
                    log.product_id AS product_id,
                    pp.default_code AS product_code,
                    log.customs_status_new AS customs_status,
                    log.mrn_status_new AS mrn_status,
                    io.billno AS inbound_no,
                    oo.billno AS outbound_no,
                    COALESCE(lt.stock_qty, 0.0) AS stock_qty,
                    log.user_id AS user_id,
                    log.operation_time AS change_time,
                    COALESCE(log.operation_remark, log.change_reason, '') AS remark,
                    log.model_name AS source_model,
                    log.res_id AS source_res_id,
                    COALESCE(sp.t1_document_number, io.t1_document_number, oo.t1_document_number) AS t1_document_number,
                    COALESCE(sp.t1_status, io.t1_status, oo.t1_status) AS t1_status,
                    COALESCE(sp.t1_closed_date, io.t1_closed_date, oo.t1_closed_date) AS t1_closed_date
                FROM bonded_customs_mrn_audit_log log
                LEFT JOIN stock_picking sp ON sp.id = log.picking_id
                LEFT JOIN world_depot_inbound_order io ON io.id = sp.inbound_order_id
                LEFT JOIN world_depot_outbound_order oo ON oo.id = sp.outbound_order_id
                LEFT JOIN product_product pp ON pp.id = log.product_id
                LEFT JOIN ledger_total lt ON lt.mrn_id = COALESCE(log.mrn_id, sp.mrn_id, io.mrn_id, oo.mrn_id)
                WHERE COALESCE(log.mrn_id, sp.mrn_id, io.mrn_id, oo.mrn_id) IS NOT NULL
            )
        """)

class InboundOrderMrnDetailAction(models.Model):
    _inherit = "world.depot.inbound.order"
    def action_open_mrn_detail(self):
        return build_mrn_detail_action(self)


class StockPickingMrnDetailAction(models.Model):
    _inherit = "stock.picking"


    def action_open_mrn_detail(self):
        return build_mrn_detail_action(self)


class StockMoveMrnDetailAction(models.Model):
    _inherit = "stock.move"

    customs_status = fields.Selection(related="picking_id.customs_status", string="Customs Status", store=True, readonly=True, index=True)

    def action_open_mrn_detail(self):
        return build_mrn_detail_action(self)


class StockMoveLineMrnDetailAction(models.Model):
    _inherit = "stock.move.line"

    def action_open_mrn_detail(self):
        return build_mrn_detail_action(self)


class StockQuantMrnDetailAction(models.Model):
    _inherit = "stock.quant"
    def action_open_mrn_detail(self):
        return build_mrn_detail_action(self)
