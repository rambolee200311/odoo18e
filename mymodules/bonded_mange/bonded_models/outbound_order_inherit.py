from odoo import api, fields, models, _
from odoo.exceptions import ValidationError, UserError


class OutboundOrder(models.Model):
    _inherit = "world.depot.outbound.order"

    pick_type = fields.Many2one("stock.picking.type", string="Picking Type", tracking=True, domain="[('code', '=', 'outgoing'), ('warehouse_id', '=', warehouse), ('warehouse_id', '!=', False)]")
    cmr_sign_time = fields.Datetime(string="CMR Sign Time", tracking=True, copy=False, index=True, readonly=True)


    @api.onchange("warehouse")
    def onchange_warehouse_filter_pick_type(self):
        domain = [("id", "=", 0)]
        for rec in self:
            if rec.warehouse:
                domain = [("code", "=", "outgoing"), ("warehouse_id", "=", rec.warehouse.id), ("warehouse_id", "!=", False)]
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
                raise ValidationError(_("The operation type [%s] of the warehouse receipt does not belong to the warehouse [%s]; cross-warehouse configuration is prohibited.") % (rec.pick_type.display_name, rec.warehouse.display_name))



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
