from odoo import api, fields, models, _
from odoo.exceptions import ValidationError, UserError, AccessError
from odoo.addons.bonded_mange.bonded_models.new_models.customs_document_core import CUSTOMS_STATUS_SELECTION


def get_bonded_missing_fields(line):
    missing_fields = []
    if not line.origin_country:
        missing_fields.append(_("Country of Origin"))
    if line.goods_value is None or line.goods_value <= 0:
        missing_fields.append(_("Goods Value"))
    if not (line.hs_code or "").strip():
        missing_fields.append(_("HS Code"))
    if line.weight is None or line.weight <= 0:
        missing_fields.append(_("Weight"))
    if not (line.customs_code or "").strip():
        missing_fields.append(_("Customs Code"))
    return missing_fields
class InboundOrderInherit(models.Model):
    _inherit = "world.depot.inbound.order"

    _sql_constraints = [
        ("unique_identifier_unique", "unique(unique_identifier)", "Unique Identifier must be unique!"),
        ("file_identifier_unique", "unique(file_identifier)", "File Identifier must be unique!")
    ]
    pick_type = fields.Many2one("stock.picking.type", string="Picking Type", tracking=True,
                                domain="[('code', '=', 'incoming'), ('warehouse_id', '=', warehouse), ('warehouse_id', '!=', False)]")
    unique_identifier = fields.Char(string='Unique Identifier', tracking=True, copy=False, index=True, readonly=True)
    file_identifier = fields.Char(string='File Identifier', tracking=True, copy=False, index=True)
    customs_document_id = fields.Many2one("bonded.customs.document", string="Customs Document", index=True,
                                          tracking=True, copy=False)

    t1_document_number = fields.Char(string="T1 Document Number", index=True, copy=False, tracking=True)
    t1_status = fields.Selection([
        ("open", "Open"),
        ("closed", "Closed"),
    ], string="T1 Status", default="open", tracking=True, index=True)

    t1_closed_date = fields.Date(string="T1 Closed Date", tracking=True)
    customs_status = fields.Selection(CUSTOMS_STATUS_SELECTION, string="Customs Status", tracking=True, index=True)
    is_bonded = fields.Boolean(string="Bonded Warehouse", default=True, tracking=True)

    @api.constrains("customs_document_id", "mrn_id", "t1_document_number")
    def check_customs_document_mrn_t1_consistency(self):
        for rec in self:
            doc = rec.customs_document_id
            if not doc:
                continue

            if not doc.mrn_id:
                raise ValidationError(_("Customs Document must have MRN."))

            if rec.mrn_id != doc.mrn_id:
                raise ValidationError(_("MRN must match the selected Customs Document."))

            if (rec.t1_document_number or "") != (doc.t1_document_number or ""):
                raise ValidationError(_("T1 Document Number must match the selected Customs Document."))

    @api.constrains("customs_document_id")
    def checkCustomsDocumentIdConstraint(self):
        inbound_model = self.env["world.depot.inbound.order"]
        for rec in self:
            if not rec.customs_document_id:
                continue
            domain = [("id", "!=", rec.id), ("customs_document_id", "=", rec.customs_document_id.id)]
            if inbound_model.sudo().search_count(domain):
                raise ValidationError(
                    _("The selected Customs Document is already used by another inbound order and cannot be reused."))

    def action_confirm(self):
        seq_model = self.env["ir.sequence"]
        res = super().action_confirm()
        for rec in self:
            vals = {}
            seq_date = rec.date or fields.Date.context_today(rec)
            if not rec.unique_identifier:
                vals["unique_identifier"] = seq_model.next_by_code("seq.inbound.unique.identifier",
                                                                   sequence_date=seq_date) or "/"
            if not rec.file_identifier:
                vals["file_identifier"] = seq_model.next_by_code("seq.inbound.file.identifier",
                                                                 sequence_date=seq_date) or "/"
            if vals:
                rec.write(vals)

            if rec.customs_document_id and rec.unique_identifier and rec.customs_document_id.unique_identifier != rec.unique_identifier:
                rec.customs_document_id.write({"unique_identifier": rec.unique_identifier})
            if rec.customs_document_id  and rec.customs_document_id.inbound_order_id != rec.id:
                rec.customs_document_id.write({"inbound_order_id": rec.id})
            if rec.customs_document_id and rec.customs_document_id.inbound_reference != rec.reference:
                rec.customs_document_id.write({"inbound_reference": rec.reference})
        return res

    @api.constrains(
        "is_bonded",
        "inbound_order_product_ids",
    )
    def check_bonded_line_fields_on_save(self):
        for rec in self:
            if not rec.is_bonded:
                continue
            for line in rec.inbound_order_product_ids.mapped("inbound_order_product_pallet_ids"):
                missing_fields = get_bonded_missing_fields(line)
                if missing_fields:
                    raise ValidationError(
                        _("Bonded inbound line %(product)s is missing required fields: %(fields)s")
                        % {
                            "product": line.product_id.display_name or _("Unknown Product"),
                            "fields": ", ".join(missing_fields),
                        }
                    )
    @api.onchange('customs_document_id')
    def onchange_customs_document_id(self):
        for rec in self:
            doc = rec.customs_document_id
            rec.mrn_id = doc.mrn_id if doc else False
            rec.customs_status = doc.customs_status if doc else False
            rec.t1_document_number = doc.t1_document_number if doc else False
            rec.t1_status = (doc.t1_status or "open") if doc else "open"
            rec.t1_closed_date = doc.t1_closed_date if doc else False

    #海关文件状态同步
    def actionSyncCustomsDocumentMirrorVals(self):
        for rec in self:
            doc = rec.customs_document_id
            vals = {}
            target_mrn_id = doc.mrn_id.id if doc and doc.mrn_id else False
            target_customs_status = doc.customs_status if doc else False
            target_t1_document_number = doc.t1_document_number if doc else False
            target_t1_status = (doc.t1_status or "open") if doc else "open"
            target_t1_closed_date = doc.t1_closed_date if doc else False
            if rec.mrn_id.id != target_mrn_id:
                vals["mrn_id"] = target_mrn_id
            if rec.customs_status != target_customs_status:
                vals["customs_status"] = target_customs_status
            if rec.t1_document_number != target_t1_document_number:
                vals["t1_document_number"] = target_t1_document_number
            if rec.t1_status != target_t1_status:
                vals["t1_status"] = target_t1_status
            if rec.t1_closed_date != target_t1_closed_date:
                vals["t1_closed_date"] = target_t1_closed_date
            if vals:
                rec.write(vals)
        return True

    def actionSyncCustomsDocumentToInboundPicking(self):
        picking_env = self.env["stock.picking"]
        for rec in self:
            picking_ids = picking_env.sudo().search([
                ("inbound_order_id", "=", rec.id),
                ("state", "!=", "cancel"),
            ]).ids
            for picking in picking_env.browse(picking_ids):
                vals = {}
                target_doc_id = rec.customs_document_id.id if rec.customs_document_id else False
                target_mrn_id = rec.customs_document_id.mrn_id.id if rec.customs_document_id and rec.customs_document_id.mrn_id else False
                if picking.customs_document_id.id != target_doc_id:
                    vals["customs_document_id"] = target_doc_id
                if picking.mrn_id.id != target_mrn_id:
                    vals["mrn_id"] = target_mrn_id

                # 只给入库单据同步标识
                if picking.picking_type_code == "incoming":
                    if rec.unique_identifier and picking.unique_identifier != rec.unique_identifier:
                        vals["unique_identifier"] = rec.unique_identifier
                    if rec.file_identifier and picking.file_identifier != rec.file_identifier:
                        vals["file_identifier"] = rec.file_identifier

                if vals:
                    picking.write(vals)
                picking.actionSyncPickingMrnFields()
                if picking.picking_type_code == "incoming":
                    picking.action_sync_identifier_to_move_line_from_picking()
        return True

    def action_create_stock_picking(self):
        res = super().action_create_stock_picking()
        self.actionSyncCustomsDocumentToInboundPicking()
        return res


    def actionSyncInboundT1ToMrnAndQuant(self):
        picking_model = self.env["stock.picking"]
        outbound_model = self.env["world.depot.outbound.order"]
        for rec in self:
            if rec.mrn_id:
                rec.mrn_id.write({
                    "t1_document_number": rec.t1_document_number or False,
                    "t1_status": rec.t1_status or "open",
                    "t1_closed_date": rec.t1_closed_date or False,
                    "customs_status": rec.customs_status,
                    "bonded_flag": "true" if rec.is_bonded else "false",
                })
                outbound_ids = outbound_model.sudo().search(
                    [("mrn_id", "=", rec.mrn_id.id), ("state", "!=", "cancel")]).ids
                for outbound in outbound_model.browse(outbound_ids):
                    vals = {
                        "customs_status": rec.customs_status,
                        "t1_document_number": rec.t1_document_number or False,
                        "t1_status": rec.t1_status or "open",
                        "t1_closed_date": rec.t1_closed_date or False,
                        "mrn_status": rec.mrn_status or False,
                        "bonded_flag": "true" if rec.is_bonded else "false",
                        "unique_identifier": rec.unique_identifier or False,
                    }
                    write_vals = {}
                    for key, value in vals.items():
                        if outbound[key] != value:
                            write_vals[key] = value
                    if write_vals:
                        outbound.write(write_vals)

            domain = [("state", "!=", "cancel")]
            if rec.mrn_id:
                domain = ["|", ("inbound_order_id", "=", rec.id), ("mrn_id", "=", rec.mrn_id.id)] + domain
            else:
                domain.append(("inbound_order_id", "=", rec.id))

            picking_ids = picking_model.sudo().search(domain).ids
            if picking_ids:
                picking_model.browse(picking_ids).actionSyncPickingMrnFields()
        return True



    def write(self, vals):
        vals_write = dict(vals)
        need_sync_t1 = any(x in vals_write for x in ['t1_status','t1_closed_date','t1_document_number'])
        user = self.env.user
        allowed = user.has_group("bonded_mange.group_customs_admin") or user.has_group(
            "stock.group_stock_manager") or user.has_group("base.group_system")
        if any(field in vals_write for field in ["t1_status","t1_closed_date" "mrn_id", "customs_status"]):
            if not allowed:
                raise AccessError(_("Only Customs Admin / Warehouse Supervisor can modify T1 Status and T1 Closed Date."))
        res = super().write(vals_write)
        if "customs_document_id" in vals:
            self.actionSyncCustomsDocumentToInboundPicking()

        self.actionSyncInboundSnapshotToMrn()
        if need_sync_t1:
            self.actionSyncInboundT1ToMrnAndQuant()
            # 根据T1状态改变MRN状态
        if "t1_status" in vals_write:
            for rec in self:
                target_mrn_status = "declared" if rec.t1_status == "closed" else rec.getMrnStatusByCustomsStatus(
                    rec.customs_status)
                if rec.mrn_status != target_mrn_status:
                    rec.with_context(skip_t1_linkage=True).write({"mrn_status": target_mrn_status})

        return res


    def unlink(self):
        for rec in self:
            if rec.unique_identifier:
                raise UserError(_("Inbound order with Unique Identifier cannot be deleted, even in Cancel state."))
        return super().unlink()
    @api.onchange("warehouse")
    def onchange_warehouse_filter_pick_type(self):
        domain = [("id", "=", 0)]
        for rec in self:
            if rec.warehouse:
                domain = [("code", "=", "incoming"), ("warehouse_id", "=", rec.warehouse.id),
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
                raise ValidationError(_("When the warehouse is not selected, it is not allowed to set the inbound operation type."))
            if rec.pick_type and rec.warehouse and rec.pick_type.warehouse_id != rec.warehouse:
                raise ValidationError(_("The operation type [%s] of the warehouse receipt does not belong to the warehouse [%s]; cross-warehouse configuration is prohibited.") % (
                rec.pick_type.display_name, rec.warehouse.display_name))



def get_reference_vals(product):
    return {
        "origin_country": product.origin_country.id or False,
        "goods_value": product.goods_value or 0.0,
        "hs_code": product.hs_code or False,
        "weight": product.weight or 0.0,
        "customs_code": product.customs_code or False,
    }

class InboundOrderProduct(models.Model):
    _inherit = "world.depot.inbound.order.product"

    unique_identifier = fields.Char(string="Unique Identifier",related='inbound_order_id.unique_identifier', tracking=True)

class InboundOrderProductsOfPallet(models.Model):
    _inherit = "world.depot.inbound.order.products.pallet"
    #_rec_name = "unique_identifier"


    inbound_no = fields.Char(string="Inbound No", related="inbound_order_product_id.inbound_order_id.billno",
                             store=True, readonly=True, index=True)
    origin_country = fields.Many2one("res.country", string="Country of Origin", tracking=True, index=True)
    goods_value = fields.Monetary(
        string='Goods Value',
        currency_field='currency_id',
        tracking=True)
    total_goods_value = fields.Monetary(string="Total Goods Value", currency_field="currency_id", compute="_compute_total_goods_value", inverse="_inverse_total_goods_value", store=True, tracking=True)
    hs_code = fields.Char(string="HS Code", tracking=True, related = 'product_id.hs_code',readonly=True, index=True)

    customs_code = fields.Char(string="Customs Code", tracking=True,related='product_id.customs_code', readonly=True, index=True)
    currency_id = fields.Many2one(
        'res.currency',
        string='Currency',
        default=lambda self: self.env.company.currency_id)
    is_bonded = fields.Boolean(string="Bonded", related="inbound_order_product_id.inbound_order_id.is_bonded",
                               readonly=True)
    unique_identifier = fields.Char(string="Unique Identifier", related="inbound_order_product_id.unique_identifier", store=True, readonly=True, index=True, tracking=True)

    @api.depends("quantity", "goods_value")
    def _compute_total_goods_value(self):
        for rec in self:
            rec.total_goods_value = (rec.quantity or 0.0) * (rec.goods_value or 0.0)

    def _inverse_total_goods_value(self):
        for rec in self:
            if not rec.quantity:
                raise ValidationError(_("Quantity must be greater than zero before setting Total Goods Value."))
            rec.goods_value = rec.total_goods_value / rec.quantity

    def _compute_display_name(self):
        if not self.env.context.get("outbound_show_unique_identifier_only"):
            return super()._compute_display_name()
        for rec in self:
            rec.display_name = (rec.unique_identifier or "").strip()

    def name_get(self):
        if not self.env.context.get("outbound_show_unique_identifier_only"):
            return super().name_get()
        result = []
        for rec in self:
            result.append((rec.id, (rec.unique_identifier or "").strip() or "-"))
        return result

    @api.model
    def name_search(self, name="", args=None, operator="ilike", limit=100):
        if not self.env.context.get("outbound_show_unique_identifier_only"):
            return super().name_search(name=name, args=args, operator=operator, limit=limit)

        domain = list(args or [])
        domain.extend([
            ("unique_identifier", "!=", False),
            ("inbound_order_product_id.inbound_order_id.state", "=", "confirm"),
            ("inbound_order_product_id.inbound_order_id.stock_picking_id.state", "=", "done"),
        ])

        warehouse_id = self.env.context.get("outbound_warehouse_id")
        if warehouse_id:
            domain.append(("inbound_order_product_id.inbound_order_id.warehouse", "=", warehouse_id))

        if name:
            domain.extend([
                "|", "|", "|", "|",
                ("unique_identifier", operator, name),
                ("product_id.display_name", operator, name),
                ("product_id.default_code", operator, name),
                ("product_id.barcode", operator, name),
                ("inbound_order_product_id.inbound_order_id.billno", operator, name),
            ])

        pallet_model = self.env["world.depot.inbound.order.products.pallet"]
        records = pallet_model.sudo().search(domain, order="id desc", limit=limit)
        return records.name_get()

    @api.constrains(
        "origin_country",
        "goods_value",
        "hs_code",
        "weight",
        "customs_code",
        "inbound_order_product_id",
    )
    def check_bonded_required_fields(self):
        for rec in self:
            order = rec.inbound_order_product_id.inbound_order_id
            if not order or not order.is_bonded:
                continue
            missing_fields = get_bonded_missing_fields(rec)
            if missing_fields:
                raise ValidationError(
                    _("Bonded inbound line %(product)s is missing required fields: %(fields)s")
                    % {
                        "product": rec.product_id.display_name or _("Unknown Product"),
                        "fields": ", ".join(missing_fields),
                    }
                )
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

    def unlink(self):
        for rec in self:
            if rec.unique_identifier:
                raise UserError(_("Inbound order with Unique Identifier cannot be deleted, even in Cancel state."))
        return super().unlink()
