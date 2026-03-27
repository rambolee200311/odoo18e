from odoo import api, fields, models, tools, _
from odoo.exceptions import UserError


CUSTOMS_STATUS_SELECTION = [
    ("vrij", "Vrij"),
    ("rto", "Return to Origin"),
    ("entrepot", "Bonded Warehouse"),
    ("accijns", "Excise Goods"),
    ("ivv", "Import/Export/Transit"),
    ("ivv_equivalent", "IVV en equivalentieverkeer"),
    ("bonded", "Bonded"),
    ("non_bonded", "Free / Non-bonded"),
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
    mrn_code = (rec.mrn_code or "").strip().upper()
    if not mrn_code:
        raise UserError(_("MRN Code is empty."))
    action = rec.env["ir.actions.actions"]._for_xml_id("bonded_mange.action_bonded_mrn_regulatory_report")
    action["name"] = _("MRN Detail: %s") % mrn_code
    action["domain"] = [("mrn_code", "=", mrn_code)]
    action["context"] = {"search_default_mrn_code": mrn_code}
    return action


class BondedMrnRegulatoryReport(models.Model):
    _name = "bonded.mrn.regulatory.report"
    _description = "MRN Regulatory Report"
    _auto = False
    _order = "id desc"

    record_type = fields.Selection([("flow", "Flow"), ("log", "Log")], string="Record Type", index=True, readonly=True)
    mrn_code = fields.Char(string="MRN Code", index=True, readonly=True)
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

    def action_open_source(self):
        self.ensure_one()
        if not self.source_model or not self.source_res_id:
            raise UserError(_("No source record to open."))
        return {"type": "ir.actions.act_window", "res_model": self.source_model, "res_id": self.source_res_id, "view_mode": "form", "target": "current"}

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute(f"""
            CREATE OR REPLACE VIEW {self._table} AS (
                WITH quant_summary AS (
                    SELECT sq.mrn_code, sq.product_id, SUM(sq.quantity) AS stock_qty, MIN(sq.customs_status) AS customs_status
                    FROM stock_quant sq
                    WHERE sq.mrn_code IS NOT NULL AND sq.mrn_code <> ''
                    GROUP BY sq.mrn_code, sq.product_id
                ),
                quant_total AS (
                    SELECT sq.mrn_code, SUM(sq.quantity) AS stock_qty
                    FROM stock_quant sq
                    WHERE sq.mrn_code IS NOT NULL AND sq.mrn_code <> ''
                    GROUP BY sq.mrn_code
                )
                SELECT
                    sml.id AS id,
                    'flow'::varchar AS record_type,
                    sml.mrn_code AS mrn_code,
                    sml.product_id AS product_id,
                    pp.default_code AS product_code,
                    COALESCE(qs.customs_status, pp.customs_status) AS customs_status,
                    COALESCE(sml.mrn_status, sp.mrn_status, io.mrn_status) AS mrn_status,
                    io.billno AS inbound_no,
                    oo.billno AS outbound_no,
                    COALESCE(qs.stock_qty, 0.0) AS stock_qty,
                    COALESCE(sml.create_uid, sp.create_uid) AS user_id,
                    COALESCE(sml.date, sp.date_done, sp.create_date) AS change_time,
                    COALESCE(sp.origin, sml.reference, '') AS remark,
                    'stock.move.line'::varchar AS source_model,
                    sml.id AS source_res_id
                FROM stock_move_line sml
                LEFT JOIN stock_picking sp ON sp.id = sml.picking_id
                LEFT JOIN world_depot_inbound_order io ON io.id = sp.inbound_order_id
                LEFT JOIN world_depot_outbound_order oo ON oo.id = sp.outbound_order_id
                LEFT JOIN product_product pp ON pp.id = sml.product_id
                LEFT JOIN quant_summary qs ON qs.mrn_code = sml.mrn_code AND qs.product_id = sml.product_id
                WHERE sml.mrn_code IS NOT NULL AND sml.mrn_code <> ''

                UNION ALL

                SELECT
                    -log.id AS id,
                    'log'::varchar AS record_type,
                    log.mrn_code AS mrn_code,
                    log.product_id AS product_id,
                    pp.default_code AS product_code,
                    log.customs_status_new AS customs_status,
                    log.mrn_status_new AS mrn_status,
                    io.billno AS inbound_no,
                    oo.billno AS outbound_no,
                    COALESCE(qt.stock_qty, 0.0) AS stock_qty,
                    log.user_id AS user_id,
                    log.operation_time AS change_time,
                    COALESCE(log.operation_remark, log.change_reason, '') AS remark,
                    log.model_name AS source_model,
                    log.res_id AS source_res_id
                FROM bonded_customs_mrn_audit_log log
                LEFT JOIN stock_picking sp ON sp.id = log.picking_id
                LEFT JOIN world_depot_inbound_order io ON io.id = sp.inbound_order_id
                LEFT JOIN world_depot_outbound_order oo ON oo.id = sp.outbound_order_id
                LEFT JOIN product_product pp ON pp.id = log.product_id
                LEFT JOIN quant_total qt ON qt.mrn_code = log.mrn_code
                WHERE log.mrn_code IS NOT NULL AND log.mrn_code <> ''
            )
        """)


class InboundOrderMrnDetailAction(models.Model):
    _inherit = "world.depot.inbound.order"
    def action_open_mrn_detail(self):
        return build_mrn_detail_action(self)


class StockPickingMrnDetailAction(models.Model):
    _inherit = "stock.picking"

    customs_status = fields.Selection(CUSTOMS_STATUS_SELECTION, string="Customs Status", compute="_compute_customs_status", store=True, index=True)

    @api.depends("inbound_order_id", "inbound_order_id.is_bonded")
    def _compute_customs_status(self):
        for rec in self:
            rec.customs_status = "bonded" if rec.inbound_order_id and rec.inbound_order_id.is_bonded else ("vrij" if rec.inbound_order_id else False)

    def action_open_mrn_detail(self):
        return build_mrn_detail_action(self)


class StockMoveMrnDetailAction(models.Model):
    _inherit = "stock.move"

    customs_status = fields.Selection(related="product_id.customs_status", string="Customs Status", store=True, readonly=True, index=True)

    def action_open_mrn_detail(self):
        return build_mrn_detail_action(self)


class StockMoveLineMrnDetailAction(models.Model):
    _inherit = "stock.move.line"

    customs_status = fields.Selection(related="product_id.customs_status", string="Customs Status", store=True, readonly=True, index=True)

    def action_open_mrn_detail(self):
        return build_mrn_detail_action(self)


class StockQuantMrnDetailAction(models.Model):
    _inherit = "stock.quant"
    def action_open_mrn_detail(self):
        return build_mrn_detail_action(self)
