import re

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError, UserError, AccessError


# 新增两套序列 ir.sequence：unique_identifier（唯一标识号）和 file_identifier（档案编号）。
# 序列规则支持格式化（如 IO-YYYYMMDD-0001），确保连续、不回收、不重复。
# 在 inbound order 创建时自动生成 unique_identifier，同时自动生成 file_identifier（可后续人工改）。
# 入库单取消只改 state='cancel'，编号永久保留，不重置不复用。
# 在 stock.picking / stock.move / stock.move.line / stock.quant 增加 unique_identifier 并与入库单绑定传递。
# 在 stock.picking / stock.quant 增加 file_identifier，默认自动带出，但允许仓管/运维手工编辑。
# 在相关 list/form 视图加字段展示，并加筛选条件（按唯一标识号、档案编号、单号查询）。
# 扩展库存履历（stock.quant.history 相关视图/模型）增加：unique_identifier、file_identifier、IO、OO。
# 履历里 IO/OO 字段做可点击关联跳转到对应 stock.picking 详情。
# 履历默认按操作时间倒序，保留全量历史记录（不做删除/覆盖）。
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

    def action_confirm(self):
        for rec in self:
            if not rec.is_bonded:
                continue
            error_lines = []
            line_no = 1
            for line in rec.inbound_order_product_ids.mapped("inbound_order_product_pallet_ids"):
                missing_fields = get_bonded_missing_fields(line)
                if missing_fields:
                    error_lines.append(
                        _("Line %(line_no)s (%(product)s): %(fields)s")
                        % {
                            "line_no": line_no,
                            "product": line.product_id.display_name or _("Unknown Product"),
                            "fields": ", ".join(missing_fields),
                        }
                    )
                line_no += 1
            if error_lines:
                raise UserError(
                    _("Bonded inbound cannot be confirmed. Please fill required fields first:\n%s")
                    % "\n".join(error_lines)
                )
        return super().action_confirm()



    @api.model
    def create(self, vals):
        seq_date = vals.get('date') or fields.Date.context_today(self)
        if not vals.get('unique_identifier'):
            vals['unique_identifier'] = self.env['ir.sequence'].next_by_code('seq.inbound.unique.identifier',
                                                                             sequence_date=seq_date) or '/'
        if not vals.get('file_identifier'):
            vals['file_identifier'] = self.env['ir.sequence'].next_by_code('seq.inbound.file.identifier',
                                                                           sequence_date=seq_date) or '/'
        return super().create(vals)

    def write(self, vals):
        vals_write = dict(vals)
        user = self.env.user
        allowed = user.has_group("bonded_mange.group_customs_admin") or user.has_group(
            "stock.group_stock_manager") or user.has_group("base.group_system")
        if any(field in vals_write for field in ["t1_status", "mrn_id", "customs_status"]):
            if not allowed:
                raise AccessError(_("Only Customs Admin / Warehouse Supervisor can modify T1 Status."))

        if "t1_status" in vals_write:
            if vals_write.get("t1_status") == "closed" and not vals_write.get("t1_closed_date"):
                vals_write["t1_closed_date"] = fields.Date.context_today(self)
            elif vals_write.get("t1_status") != "closed":
                vals_write["t1_closed_date"] = False

        res = super().write(vals_write)


        if vals_write.get("t1_status") == "closed":
            for rec in self:
                if rec.mrn_status != "declared":
                    rec.with_context(skip_t1_linkage=True).write({"mrn_status": "declared"})
                product_records = rec.inbound_order_product_ids.mapped(
                    "inbound_order_product_pallet_ids.product_id").filtered(lambda x: x)
                for product in product_records:
                    if product.customs_status not in ("bonded", "entrepot"):
                        product.write({"customs_status": "bonded"})
                picking_ids = self.env["stock.picking"].sudo().search(
                    [("inbound_order_id", "=", rec.id), ("picking_type_code", "=", "incoming")]).ids
                for picking in self.env["stock.picking"].browse(picking_ids):
                    picking.actionSyncPickingMrnFields()

        return res



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
class InboundOrderProductsOfPallet(models.Model):
    _inherit = "world.depot.inbound.order.products.pallet"

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
    is_bonded = fields.Boolean(string="Bonded", related="inbound_order_product_id.inbound_order_id.is_bonded",
                               readonly=True)

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
