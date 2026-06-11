from odoo import api, fields, models, _
from odoo.exceptions import ValidationError, UserError
from odoo.addons.bonded_mange.bonded_models.new_models.customs_document_core import CUSTOMS_STATUS_SELECTION

class OutboundOrder(models.Model):
    _inherit = "world.depot.outbound.order"

    pick_type = fields.Many2one("stock.picking.type", string="Picking Type", tracking=True,
                                domain="[('code', '=', 'outgoing'), ('warehouse_id', '=', warehouse), ('warehouse_id', '!=', False)]")
    cmr_sign_time = fields.Datetime(string="CMR Sign Time", tracking=True, copy=False, index=True, readonly=True)
    mrn_id = fields.Many2one("bonded.mrn.master", string="MRN", index=True, copy=False, tracking=True)
    #inbound_confirm_mrn_ids = fields.Many2many("bonded.mrn.master", compute="_compute_inbound_confirm_mrn_ids",compute_sudo=True)

    unique_identifier = fields.Char(string='Unique Identifier', tracking=True, copy=False, index=True, readonly=True)
    bonded_flag = fields.Selection([("true", "bonded"), ("false", "Non-bonded")], string="Bonded Flag",default='false', index=True)
    customs_document_id = fields.Many2one("bonded.customs.document", string="Customs Document", index=True,
                                          tracking=True, copy=False)


    def write(self, vals):
        res = super().write(vals)
        if "customs_document_id" in vals:
            self.actionSyncCustomsDocumentMirrorVals()
            self.actionSyncCustomsDocumentToOutboundPicking()
        return res

    def actionSyncCustomsDocumentMirrorVals(self):
        for rec in self:
            doc = rec.customs_document_id
            vals = {}
            target_customs_status = doc.customs_status if doc else False
            target_t1_document_number = doc.t1_document_number if doc else False
            target_t1_status = (doc.t1_status or "open") if doc else "open"
            target_t1_closed_date = doc.t1_closed_date if doc else False
            if "customs_status" in rec._fields and rec.customs_status != target_customs_status:
                vals["customs_status"] = target_customs_status
            if "t1_document_number" in rec._fields and rec.t1_document_number != target_t1_document_number:
                vals["t1_document_number"] = target_t1_document_number
            if "t1_status" in rec._fields and rec.t1_status != target_t1_status:
                vals["t1_status"] = target_t1_status
            if "t1_closed_date" in rec._fields and rec.t1_closed_date != target_t1_closed_date:
                vals["t1_closed_date"] = target_t1_closed_date
            if vals:
                rec.write(vals)
        return True

    def actionSyncCustomsDocumentToOutboundPicking(self):
        picking_env = self.env["stock.picking"]
        for rec in self:
            picking_ids = picking_env.sudo().search([("outbound_order_id", "=", rec.id), ("state", "!=", "cancel")]).ids
            target_doc_id = rec.customs_document_id.id if rec.customs_document_id else False
            for picking in picking_env.browse(picking_ids):
                if picking.customs_document_id.id != target_doc_id:
                    picking.write({"customs_document_id": target_doc_id})
        return True

    def action_create_picking_PICK(self):
        res = super().action_create_picking_PICK()
        self.actionSyncCustomsDocumentToOutboundPicking()
        return res

    def action_create_picking_PICK_linglong(self):
        res = super().action_create_picking_PICK_linglong()
        self.actionSyncCustomsDocumentToOutboundPicking()
        return res

    # @api.depends("mrn_id", "state")
    # def _compute_inbound_confirm_mrn_ids(self):
    #     inbound_model = self.env["world.depot.inbound.order"]
    #     outbound_model = self.env['world.depot.outbound.order']
    #
    #     inbound_mrn_ids = set(inbound_model.sudo().search(
    #         [('mrn_id', '!=', False), ('state', '=', 'confirm'), ('stock_picking_id.state', '=', 'done')]).mapped(
    #         "mrn_id").ids)
    #     used_mrn_ids = set(outbound_model.sudo().search(
    #         [("id", "not in", self.ids), ("state", "!=", "cancel"), ("mrn_id", "!=", False)]
    #     ).mapped("mrn_id").ids)
    #     available_ids = list(inbound_mrn_ids - used_mrn_ids)
    #
    #     for rec in self:
    #         rec_ids = list(available_ids)
    #         if rec.mrn_id:
    #             rec_ids.append(rec.mrn_id.id)
    #         rec.inbound_confirm_mrn_ids = [(6, 0, list(set(rec_ids)))]

    mrn_status = fields.Selection([
        ("pending_declaration", "Pending Declaration"),
        ("declared", "Declared"),
        ("cleared", "Cleared"),
        ("status_changed", "Status Changed"),
        ("exception", "Exception"),
    ], string="MRN Status", index=True, copy=False, tracking=True)
    customs_status = fields.Selection(CUSTOMS_STATUS_SELECTION, string="Customs Status", index=True, tracking=True)
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
                "project": inbound.project.id or False,
                "warehouse": inbound.warehouse.id or False,
                "bonded_flag": mrn.bonded_flag or "false",
            }
        return {
            "mrn_status": mrn.mrn_status or False,
            "project": False,
            "warehouse": False,
            "bonded_flag": mrn.bonded_flag or "false",
        }


    @api.onchange("mrn_id")
    def onchangeMrnId(self):
        for rec in self:
            if rec.mrn_id:
                vals = rec.actionGetMrnMirrorVals(rec.mrn_id)

                rec.mrn_status = vals["mrn_status"]
                rec.bonded_flag = vals["bonded_flag"]
                if vals.get("project"):
                    rec.project = vals["project"]
                if vals.get("warehouse"):
                    rec.warehouse = vals["warehouse"]
                if rec.pick_type and rec.warehouse and rec.pick_type.warehouse_id != rec.warehouse:
                    rec.pick_type = False
            else:
                rec.mrn_status = False


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

    inbound_pallet_id = fields.Many2one(
        "world.depot.inbound.order.products.pallet",
        string="Inbound Pallet Line(Unique Identifier)",
        tracking=True,
        copy=False,
        index=True,
        domain="[('product_id', '=', product_id),"
               " ('inbound_order_product_id.inbound_order_id.state', '=', 'confirm'),"
               " ('inbound_order_product_id.inbound_order_id.stock_picking_id.state', '=', 'done')]",
    )
    unique_identifier = fields.Char(string="Unique Identifier", related="inbound_pallet_id.unique_identifier",
                                    store=True, readonly=True, tracking=True, index=True)

    @api.constrains("inbound_pallet_id", "product_id")
    def check_inbound_pallet_product_match(self):
        for rec in self:
            if rec.inbound_pallet_id and rec.product_id and rec.inbound_pallet_id.product_id != rec.product_id:
                raise ValidationError(_("Inbound Pallet Line product does not match outbound line product."))

    @api.onchange("product_id")
    def onchange_product_id_clear_inbound_pallet_id(self):
        for rec in self:
            if rec.inbound_pallet_id and rec.product_id and rec.inbound_pallet_id.product_id != rec.product_id:
                rec.inbound_pallet_id = False

    @api.onchange("product_id")
    def onchange_auto_assign_inbound_pallet_id(self):
        for rec in self:
            if not rec.product_id or not rec.outbound_order_id or rec.inbound_pallet_id:
                continue
            order = rec.outbound_order_id
            if not order.get_is_bonded_outbound_order():
                continue
            qty_map = order.action_get_ledger_qty_map_by_product_unique([rec.product_id.id])
            if not qty_map:
                continue
            unique_list = sorted({k[1] for k in qty_map.keys() if k[1]})
            pallet_map = order.action_get_inbound_pallet_map_by_product_unique([rec.product_id.id],
                                                                               unique_list=unique_list,
                                                                               bonded_value=True)
            candidate_list = [uid for uid in unique_list if (rec.product_id.id, uid) in pallet_map and float(
                qty_map.get((rec.product_id.id, uid)) or 0.0) > 0]
            if candidate_list:
                rec.inbound_pallet_id = pallet_map[(rec.product_id.id, candidate_list[0])].id


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
        outbound_model = self.env["world.depot.outbound.order"].sudo()
        for vals in vals_list:
            vals.pop("unique_identifier", None)
            product_id = vals.get("product_id")
            if not product_id:
                continue
            order_id = vals.get("outbound_order_id")
            if order_id and not vals.get("inbound_pallet_id") and vals.get("unique_identifier"):
                outbound = outbound_model.browse(order_id)
                unique_text = (vals.get("unique_identifier") or "").strip()
                if unique_text:
                    pallet_map = outbound.action_get_inbound_pallet_map_by_product_unique(
                        [product_id],
                        unique_list=[unique_text],
                        bonded_value=outbound.get_is_bonded_outbound_order(),
                    )
                    pallet = pallet_map.get((product_id, unique_text))
                    if pallet:
                        vals["inbound_pallet_id"] = pallet.id
            vals_ref = get_reference_vals(product_env.browse(product_id))
            vals.setdefault("origin_country", vals_ref["origin_country"])
            vals.setdefault("goods_value", vals_ref["goods_value"])
            vals.setdefault("weight", vals_ref["weight"])
            vals["hs_code"] = vals_ref["hs_code"]
            vals["customs_code"] = vals_ref["customs_code"]
        return super().create(vals_list)

    def write(self, vals):
        vals_write = dict(vals)
        if ("hs_code" in vals_write or "customs_code" in vals_write) and "product_id" not in vals_write:
            raise UserError(_("HS Code and Customs Code are reference values and cannot be modified."))

        if "unique_identifier" in vals_write and "inbound_pallet_id" not in vals_write:
            unique_text = (vals_write.get("unique_identifier") or "").strip()
            vals_write.pop("unique_identifier", None)
            if not unique_text:
                vals_write["inbound_pallet_id"] = False
            else:
                if len(self) != 1:
                    raise ValidationError(_("Batch write with unique_identifier is not supported."))
                rec = self[0]
                product_id = vals_write.get("product_id") or rec.product_id.id
                order = rec.outbound_order_id
                pallet_map = order.action_get_inbound_pallet_map_by_product_unique(
                    [product_id],
                    unique_list=[unique_text],
                    bonded_value=order.get_is_bonded_outbound_order(),
                )
                pallet = pallet_map.get((product_id, unique_text))
                if not pallet:
                    raise ValidationError(_("Cannot find inbound pallet for Unique Identifier [%s].") % unique_text)
                vals_write["inbound_pallet_id"] = pallet.id

        if vals_write.get("product_id"):
            product = self.env["product.product"].sudo().browse(vals_write["product_id"])
            vals_ref = get_reference_vals(product)
            vals_write["hs_code"] = vals_ref["hs_code"]
            vals_write["customs_code"] = vals_ref["customs_code"]
            vals_write.setdefault("origin_country", vals_ref["origin_country"])
            vals_write.setdefault("goods_value", vals_ref["goods_value"])
            vals_write.setdefault("weight", vals_ref["weight"])
            if "inbound_pallet_id" not in vals_write:
                vals_write["inbound_pallet_id"] = False

        return super().write(vals_write)
