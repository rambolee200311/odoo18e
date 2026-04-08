from odoo import api, fields, models, _
from odoo.exceptions import ValidationError, UserError


class OutboundOrder(models.Model):
    _inherit = "world.depot.outbound.order"

    pick_type = fields.Many2one("stock.picking.type", string="Picking Type", tracking=True,
                                domain="[('code', '=', 'outgoing'), ('warehouse_id', '=', warehouse), ('warehouse_id', '!=', False)]")
    cmr_sign_time = fields.Datetime(string="CMR Sign Time", tracking=True, copy=False, index=True, readonly=True)
    mrn_id = fields.Many2one("bonded.mrn.master", string="MRN", index=True, copy=False, tracking=True,
                             domain="[('id', 'in', inbound_confirm_mrn_ids)]")
    inbound_confirm_mrn_ids = fields.Many2many("bonded.mrn.master", compute="_compute_inbound_confirm_mrn_ids",
                                               compute_sudo=True)
    unique_identifier = fields.Char(string='Unique Identifier', tracking=True, copy=False, index=True, readonly=True)
    bonded_flag = fields.Selection([("true", "bonded"), ("false", "Non-bonded")], string="Bonded Flag", index=True, default="false", readonly=True)

    @api.depends("mrn_id", "state")
    def _compute_inbound_confirm_mrn_ids(self):
        inbound_model = self.env["world.depot.inbound.order"]
        outbound_model = self.env['world.depot.outbound.order']

        inbound_mrn_ids = set(inbound_model.sudo().search(
            [('mrn_id', '!=', False), ('state', '=', 'confirm'), ('stock_picking_id.state', '=', 'done')]).mapped(
            "mrn_id").ids)
        used_mrn_ids = set(outbound_model.sudo().search(
            [("id", "not in", self.ids), ("state", "!=", "cancel"), ("mrn_id", "!=", False)]
        ).mapped("mrn_id").ids)
        available_ids = list(inbound_mrn_ids - used_mrn_ids)

        for rec in self:
            rec_ids = list(available_ids)
            if rec.mrn_id:
                rec_ids.append(rec.mrn_id.id)
            rec.inbound_confirm_mrn_ids = [(6, 0, list(set(rec_ids)))]

    mrn_status = fields.Selection([
        ("pending_declaration", "Pending Declaration"),
        ("declared", "Declared"),
        ("cleared", "Cleared"),
        ("status_changed", "Status Changed"),
        ("exception", "Exception"),
    ], string="MRN Status", index=True, copy=False, tracking=True)
    customs_status = fields.Selection([
        ("vrij", "Vrij"),
        ("rto", "Return to Origin"),
        ("entrepot", "Bonded Warehouse"),
        ("accijns", "Excise Goods"),
        ("ivv", "Import/Export/Transit & Equivalent"),
    ], string="Customs Status", index=True, tracking=True)
    t1_document_number = fields.Char(string="T1 Document Number", index=True, copy=False, tracking=True)
    t1_status = fields.Selection([("open", "Open"), ("closed", "Closed")], string="T1 Status", default="open",
                                 index=True, tracking=True)
    t1_closed_date = fields.Date(string="T1 Closed Date", index=True, tracking=True)

    def actionGetMrnMirrorVals(self, mrn):
        inbound = self.env["world.depot.inbound.order"].sudo().search([
            ("mrn_id", "=", mrn.id),
            ("state", "=", "confirm"),
            ("stock_picking_id.state", "=", "done"),
        ], order="id desc", limit=1)
        if inbound:
            return {
                "mrn_status": inbound.mrn_status or False,
                "unique_identifier": inbound.unique_identifier or False,
                "customs_status": "vrij" if inbound.is_bonded else "",
                "t1_document_number": inbound.t1_document_number or False,
                "t1_status": inbound.t1_status or "open",
                "t1_closed_date": inbound.t1_closed_date or False,
                "project": inbound.project.id or False,
                "warehouse": inbound.warehouse.id or False,
                "bonded_flag": mrn.bonded_flag or "false",
            }
        return {
            "mrn_status": mrn.mrn_status or False,
            "unique_identifier": inbound.unique_identifier or False,
            "customs_status": mrn.customs_status or False,
            "t1_document_number": mrn.t1_document_number or False,
            "t1_status": mrn.t1_status or "open",
            "t1_closed_date": mrn.t1_closed_date or False,
            "project": False,
            "warehouse": False,
            "bonded_flag": mrn.bonded_flag or "false",
        }

    def getMrnQuantGroupData(self):
        self.ensure_one()
        quant_env = self.env["stock.quant"]
        domain = [("mrn_id", "=", self.mrn_id.id), ("quantity", ">", 0), ("location_id.usage", "=", "internal")]
        if self.warehouse and self.warehouse.view_location_id:
            domain.append(("location_id", "child_of", self.warehouse.view_location_id.id))
        return quant_env.sudo().read_group(domain, ["product_id", "quantity:sum"], ["product_id"], lazy=False)

    def getOutboundLineCommandsByMrn(self):
        self.ensure_one()
        line_commands = [(5, 0, 0)]
        if not self.mrn_id or not self.warehouse or not self.warehouse.view_location_id:
            return line_commands
        quant_group_list = self.getMrnQuantGroupData()
        for item in quant_group_list:
            if not item.get("product_id"):
                continue
            product_id = item["product_id"][0]
            qty = float(item.get("quantity") or 0.0)
            if qty <= 0:
                continue
            line_commands.append((0, 0, {
                "product_id": product_id,
                "quantity": qty,
                "pallets": 1.0,
                "remark": _("Auto generated by MRN: %s") % (self.mrn_id.code or ""),
            }))
        return line_commands

    def actionReloadOutboundLinesByMrn(self):
        for rec in self:
            if rec.state != "new":
                raise ValidationError(_("Only draft outbound orders can reload MRN lines."))
            if not rec.mrn_id:
                raise ValidationError(_("Please select MRN first."))
            if not rec.warehouse or not rec.warehouse.view_location_id:
                raise ValidationError(_("Please select warehouse first."))
            rec.write({"outbound_order_product_ids": rec.getOutboundLineCommandsByMrn()})

    @api.onchange("mrn_id")
    def onchangeMrnId(self):
        for rec in self:
            if rec.mrn_id:
                vals = rec.actionGetMrnMirrorVals(rec.mrn_id)
                rec.unique_identifier = vals["unique_identifier"]
                rec.mrn_status = vals["mrn_status"]
                rec.t1_document_number = vals["t1_document_number"]
                rec.t1_status = vals["t1_status"]
                rec.t1_closed_date = vals["t1_closed_date"]
                rec.bonded_flag = vals["bonded_flag"]
                if vals.get("project"):
                    rec.project = vals["project"]
                if vals.get("warehouse"):
                    rec.warehouse = vals["warehouse"]
                if rec.pick_type and rec.warehouse and rec.pick_type.warehouse_id != rec.warehouse:
                    rec.pick_type = False
            else:
                rec.mrn_status = False
                rec.t1_document_number = False
                rec.t1_status = "open"
                rec.t1_closed_date = False
            if rec.state == "new":
                rec.outbound_order_product_ids = rec.getOutboundLineCommandsByMrn()

    @api.onchange("warehouse")
    def onchange_warehouse_filter_pick_type(self):
        domain = [("id", "=", 0)]
        for rec in self:
            if rec.warehouse:
                domain = [("code", "=", "outgoing"), ("warehouse_id", "=", rec.warehouse.id),
                          ("warehouse_id", "!=", False)]
                if rec.pick_type and rec.pick_type.warehouse_id != rec.warehouse:
                    rec.pick_type = False
            else:
                rec.pick_type = False
        return {"domain": {"pick_type": domain}}

    @api.constrains("warehouse", "pick_type")
    def check_warehouse_pick_type_binding(self):
        for rec in self:
            if rec.pick_type and not rec.warehouse:
                raise ValidationError(
                    _("When the warehouse is not selected, it is not allowed to set the inbound operation type."))
            if rec.pick_type and rec.warehouse and rec.pick_type.warehouse_id != rec.warehouse:
                raise ValidationError(
                    _("The operation type [%s] of the warehouse receipt does not belong to the warehouse [%s]; cross-warehouse configuration is prohibited.") % (
                    rec.pick_type.display_name, rec.warehouse.display_name))


def get_reference_vals(product):
    return {
        "origin_country": product.origin_country.id or False,
        "goods_value": product.goods_value or 0.0,
        "hs_code": product.hs_code or False,
        "weight": product.weight or 0.0,
        "customs_code": product.customs_code or False,
    }


class OutboundOrderProduct(models.Model):
    _inherit = "world.depot.outbound.order.product"

    origin_country = fields.Many2one("res.country", string="Country of Origin", tracking=True, index=True)
    goods_value = fields.Monetary(
        string='Goods Value',
        currency_field='currency_id',
        tracking=True)
    hs_code = fields.Char(string="HS Code", tracking=True, readonly=True, index=True)
    weight = fields.Float(string="Weight", tracking=True)
    customs_code = fields.Char(string="Customs Code", tracking=True, readonly=True, index=True)
    currency_id = fields.Many2one(
        'res.currency',
        string='Currency',
        default=lambda self: self.env.company.currency_id)

    @api.onchange("product_id")
    def onchange_product_id_fill_reference_fields(self):
        for rec in self:
            if rec.product_id:
                vals = get_reference_vals(rec.product_id)
                rec.origin_country = vals["origin_country"]
                rec.goods_value = vals["goods_value"]
                rec.hs_code = vals["hs_code"]
                rec.weight = vals["weight"]
                rec.customs_code = vals["customs_code"]

    @api.model_create_multi
    def create(self, vals_list):
        product_env = self.env["product.product"].sudo()
        for vals in vals_list:
            product_id = vals.get("product_id")
            if not product_id:
                continue
            vals_ref = get_reference_vals(product_env.browse(product_id))
            vals.setdefault("origin_country", vals_ref["origin_country"])
            vals.setdefault("goods_value", vals_ref["goods_value"])
            vals.setdefault("weight", vals_ref["weight"])
            vals["hs_code"] = vals_ref["hs_code"]
            vals["customs_code"] = vals_ref["customs_code"]
        return super().create(vals_list)

    def write(self, vals):
        if ("hs_code" in vals or "customs_code" in vals) and "product_id" not in vals:
            raise UserError(_("HS Code and Customs Code are reference values and cannot be modified."))
        if vals.get("product_id"):
            product = self.env["product.product"].sudo().browse(vals["product_id"])
            vals_ref = get_reference_vals(product)
            vals = dict(vals)
            vals["hs_code"] = vals_ref["hs_code"]
            vals["customs_code"] = vals_ref["customs_code"]
            vals.setdefault("origin_country", vals_ref["origin_country"])
            vals.setdefault("goods_value", vals_ref["goods_value"])
            vals.setdefault("weight", vals_ref["weight"])
        return super().write(vals)
