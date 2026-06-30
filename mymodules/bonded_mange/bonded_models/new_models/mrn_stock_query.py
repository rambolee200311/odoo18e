# /.../bonded_models/mrn_stock_query.py
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError
from odoo.addons.bonded_mange.bonded_models.new_models.customs_document_core import CUSTOMS_STATUS_SELECTION
MRN_STATUS_SELECTION = [("pending_declaration", "Pending Declaration"),
                        ("declared", "Declared"),
                        ("cleared", "Cleared"),
                        ("status_changed", "Status Changed"),
                        ("exception", "Exception")]

class BondedMrnStockQuery(models.Model):
    _name = "bonded.mrn.stock.query"
    _description = "MRN Product Stock Query"
    _order = "id desc"

    name = fields.Char(string="Name", required=True, copy=False, default=lambda self: _("New Query"), index=True)
    start_time = fields.Datetime(string="Start Time", required=True, index=True, copy=False)
    end_time = fields.Datetime(string="End Time", required=True, index=True, copy=False)
    product_id = fields.Many2one("product.product", string="Product", index=True, options="{'no_create': True, 'no_open': True}")
    mrn_id = fields.Many2one("bonded.mrn.master", string="MRN", store=True, index=True)
    query_lines = fields.One2many("bonded.mrn.stock.query.line", "query_id", string="Query Lines", copy=False)
    state = fields.Selection([("draft", "Draft"), ("done", "Done")], string="State", default="draft", index=True, copy=False)
    company_id = fields.Many2one("res.company", string="Company", default=lambda self: self.env.company, index=True, copy=False)
    unique_identifier = fields.Char(string='Unique Identifier', tracking=True, copy=False, index=True)

    def actionPrintPdf(self):
        self.ensure_one()
        return self.env.ref("bonded_mange.action_report_bonded_mrn_stock_query_pdf").report_action(self)



    @api.constrains("start_time", "end_time")
    def checkDateRange(self):
        for rec in self:
            if rec.start_time and rec.end_time and rec.start_time > rec.end_time:
                raise ValidationError(_("Start Time cannot be later than End Time."))

    def actionBackToDraft(self):
        for rec in self:
            if rec.state != "done":
                continue
            if not self.env.user.has_group("base.group_system"):
                raise ValidationError(_("Only administrators can reset to Draft."))
            rec.write({"state": "draft"})
        return True

    def action_query_mrn_stock(self):
        line_model = self.env["stock.move.line"]
        product_model = self.env["product.product"]
        mrn_model = self.env["bonded.mrn.master"]

        for rec in self:
            rec.query_lines.unlink()
            query_unique = (rec.unique_identifier or "").strip()

            domain_line = [
                ("state", "=", "done"),
                ("date", "<=", rec.end_time),
                ("picking_id.picking_type_id.code", "in", ["incoming", "outgoing"]),
            ]
            if rec.product_id:
                domain_line.append(("product_id", "=", rec.product_id.id))
            if rec.mrn_id:
                domain_line.append(("mrn_id", "=", rec.mrn_id.id))
            if query_unique:
                domain_line.append(("unique_identifier", "=", query_unique))

            line_list = line_model.sudo().search(domain_line, order="date asc,id asc")
            data_map = {}

            for sml in line_list:
                if not sml.product_id:
                    continue

                pick_code = sml.picking_id.picking_type_id.code if sml.picking_id and sml.picking_id.picking_type_id else False
                if pick_code not in ("incoming", "outgoing"):
                    continue

                mrn_id = sml.mrn_id.id or False
                product_id = sml.product_id.id
                unique_identifier = (sml.unique_identifier or "").strip() or False

                inbound_no = (
                    sml.picking_id.inbound_order_id.billno
                    if sml.picking_id and sml.picking_id.inbound_order_id
                    else False
                )
                outbound_no = (
                    sml.picking_id.outbound_order_id.billno
                    if sml.picking_id and sml.picking_id.outbound_order_id
                    else False
                )
                order_no = inbound_no if pick_code == "incoming" else outbound_no
                if not order_no:
                    order_no = sml.picking_id.name if sml.picking_id else False

                # 关键：不同入库/出库单不合并
                key = (mrn_id, product_id, unique_identifier, pick_code, order_no)

                if key not in data_map:
                    data_map[key] = {
                        "mrn_id": mrn_id,
                        "product_id": product_id,
                        "unique_identifier": unique_identifier,
                        "customs_status": sml.customs_status or False,
                        "mrn_status": sml.mrn_status or False,
                        "inbound_no": order_no if pick_code == "incoming" else False,
                        "outbound_no": order_no if pick_code == "outgoing" else False,
                        "opening_qty": 0.0,
                        "inbound_qty": 0.0,
                        "outbound_qty": 0.0,
                        "stock_qty": 0.0,
                        "available_stock_qty": 0.0,
                        "operator_id": False,
                        "change_time": False,
                        "remark": False,
                        "latest_time": False,
                    }

                item = data_map[key]
                qty = float(sml.quantity or 0.0)

                if sml.date < rec.start_time:
                    if pick_code == "incoming":
                        item["opening_qty"] += qty
                    else:
                        item["opening_qty"] -= qty
                else:
                    if pick_code == "incoming":
                        item["inbound_qty"] += qty
                    else:
                        item["outbound_qty"] += qty

                if (not item["latest_time"]) or sml.date >= item["latest_time"]:
                    item["latest_time"] = sml.date
                    item["operator_id"] = sml.create_uid.id if sml.create_uid else False
                    item["change_time"] = sml.date
                    item["remark"] = (
                            (sml.picking_id.inbound_order_id.billno if sml.picking_id and sml.picking_id.inbound_order_id else False)
                            or (
                                sml.picking_id.outbound_order_id.billno if sml.picking_id and sml.picking_id.outbound_order_id else False)
                            or False)
                    item["customs_status"] = sml.customs_status or item["customs_status"]
                    item["mrn_status"] = sml.mrn_status or item["mrn_status"]

            product_ids = list({x["product_id"] for x in data_map.values() if x.get("product_id")})
            mrn_ids = list({x["mrn_id"] for x in data_map.values() if x.get("mrn_id")})
            product_map = {p.id: p for p in product_model.sudo().browse(product_ids)}
            mrn_map = {m.id: m for m in mrn_model.sudo().browse(mrn_ids)}

            # 同一 mrn+product+unique 的可用库存（跨单据汇总）
            available_map = {}
            for item in data_map.values():
                base_key = (item["product_id"], item["unique_identifier"])
                delta_qty = (item["opening_qty"] or 0.0) + (item["inbound_qty"] or 0.0) - (item["outbound_qty"] or 0.0)
                available_map[base_key] = float(available_map.get(base_key) or 0.0) + float(delta_qty)

            vals_list = []
            for item in data_map.values():
                item["stock_qty"] = item["opening_qty"] + item["inbound_qty"] - item["outbound_qty"]
                base_key = (item["product_id"], item["unique_identifier"])
                item["available_stock_qty"] = float(available_map.get(base_key) or 0.0)


                mrn = mrn_map.get(item["mrn_id"]) if item["mrn_id"] else False
                uid = (item["unique_identifier"] or "").strip()
                customs_doc = self.env["bonded.customs.document"].sudo().search([("unique_identifier", "=", uid)],
                                                                                order="id desc",
                                                                                limit=1) if uid else False
                customs_status = item["customs_status"] or (customs_doc.customs_status if customs_doc else False)
                mrn_status = item["mrn_status"] or (mrn.mrn_status if mrn else False)

                vals_list.append({
                    "query_id": rec.id,
                    "mrn_id": item["mrn_id"] or False,
                    "unique_identifier": item["unique_identifier"] or False,
                    "product_id": item["product_id"],
                    "customs_status": customs_status,
                    "mrn_status": mrn_status,
                    "inbound_no": item["inbound_no"],
                    "outbound_no": item["outbound_no"],
                    "opening_qty": item["opening_qty"],
                    "inbound_qty": item["inbound_qty"],
                    "outbound_qty": item["outbound_qty"],
                    "stock_qty": item["stock_qty"],
                    "available_stock_qty": item["available_stock_qty"],
                    "operator_id": item["operator_id"],
                    "change_time": item["change_time"],
                    "remark": item["remark"],
                })

            if vals_list:
                self.env["bonded.mrn.stock.query.line"].create(vals_list)
            rec.state = "done"

        return True


class BondedMrnStockQueryLine(models.Model):
    _name = "bonded.mrn.stock.query.line"
    _description = "MRN Product Stock Query Line"
    _order = "id desc"

    query_id = fields.Many2one("bonded.mrn.stock.query", string="Query", required=True, ondelete="cascade", index=True)
    mrn_id = fields.Many2one("bonded.mrn.master", string="MRN", store=True, readonly=True, index=True)
    unique_identifier = fields.Char(string='Unique Identifier', tracking=True, copy=False, index=True)
    product_id = fields.Many2one("product.product", string="Product", required=True, index=True, options="{'no_create': True, 'no_open': True}")
    product_barcode = fields.Char(string="Product Barcode", related="product_id.barcode", readonly=True, store=True, index=True)
    product_weight = fields.Float(string="Product Weight",related='product_id.weight', readonly=True, store=True)
    event_total_weight = fields.Float(string="Event Total Weight (kg)", compute="_compute_total_weight", store=True)
    customs_status = fields.Selection(CUSTOMS_STATUS_SELECTION, string="Customs Status", index=True, readonly=True)
    mrn_status = fields.Selection(MRN_STATUS_SELECTION, string="MRN Status", index=True, readonly=True)
    inbound_no = fields.Char(string="Inbound No", index=True, readonly=True)
    outbound_no = fields.Char(string="Outbound No", index=True, readonly=True)
    opening_qty = fields.Float(string="Qty Before Start", readonly=True)
    inbound_qty = fields.Float(string="Inbound Qty", readonly=True)
    outbound_qty = fields.Float(string="Outbound Qty", readonly=True)
    stock_qty = fields.Float(string="Event Qty", readonly=True)
    available_stock_qty = fields.Float(string="Available Stock", readonly=True)
    operator_id = fields.Many2one("res.users", string="Operator", index=True, readonly=True, options="{'no_create': True, 'no_open': True}")
    change_time = fields.Datetime(string="Change Time", index=True, readonly=True)
    remark = fields.Char(string="Remark", readonly=True)

    @api.depends("product_weight", "inbound_qty", "outbound_qty", "stock_qty")
    def _compute_total_weight(self):
        for rec in self:
            rec.event_total_weight = abs(rec.stock_qty or 0.0) * (rec.product_weight or 0.0)
