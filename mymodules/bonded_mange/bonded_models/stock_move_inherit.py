
from odoo import api, fields, models, _
from odoo.exceptions import UserError

CUSTOMS_MUTATION_TYPE_SELECTION = [
    ("inbound", "Inbound"),
    ("outbound", "Outbound"),
    ("finding", "Finding"),
    ("missing", "Missing"),
    ("correction", "Correction"),
]

def get_reference_vals(product):
    return {
        "origin_country": product.origin_country.id or False,
        "goods_value": product.goods_value or 0.0,
        "hs_code": product.hs_code or False,
        "weight": product.weight or 0.0,
        "customs_code": product.customs_code or False,
    }
class StockMove(models.Model):
    _inherit = "stock.move"

    origin_country = fields.Many2one("res.country", string="Country of Origin", tracking=True, index=True)
    goods_value = fields.Monetary(
        string='Goods Value',
        currency_field='currency_id',
        tracking=True
    )
    hs_code = fields.Char(string="HS Code", tracking=True, readonly=True, index=True)
    weight = fields.Float(string="Weight", tracking=True)
    customs_code = fields.Char(string="Customs Code", tracking=True, readonly=True, index=True)
    unique_identifier = fields.Char(string='Unique Identifier', related='picking_id.unique_identifier', store=True,
                                    readonly=True, index=True)
    file_identifier = fields.Char(string="File Identifier", related="picking_id.file_identifier", store=True,
                                  readonly=True, index=True)
    currency_id = fields.Many2one(
        'res.currency',
        string='Currency',
        default=lambda self: self.env.company.currency_id)

    mrn_id = fields.Many2one("bonded.mrn.master", string="MRN", related="picking_id.mrn_id", store=True, readonly=True,
                             index=True)
    mrn_status = fields.Selection([
        ("pending_declaration", "Pending Declaration"),
        ("declared", "Declared"),
        ("cleared", "Cleared"),
        ("status_changed", "Status Changed"),
        ("exception", "Exception"),
    ], string="MRN Status", default="pending_declaration", tracking=True, copy=False, index=True)

    t1_document_number = fields.Char(string="T1 Document Number", related="picking_id.t1_document_number",
                                     store=True, index=True, copy=False)
    t1_status = fields.Selection([
        ("open", "Open"),
        ("closed", "Closed"),
    ], string="T1 Status", default="open", related="picking_id.t1_status", store=True, tracking=True, index=True)

    t1_closed_date = fields.Date(string="T1 Closed Date", related="picking_id.t1_closed_date", store=True,
                                 tracking=True)
    bonded_flag = fields.Selection([("true", "bonded"), ("false", "Non-bonded")], string="Bonded Flag", related="picking_id.bonded_flag", store=True, index=True,
                                   readonly=True)
    customs_mutation_type = fields.Selection(CUSTOMS_MUTATION_TYPE_SELECTION, string="Customs Mutation Type", tracking=True, index=True, copy=False)

    # @api.onchange("picking_id")
    # def onchange_picking_id_set_customs_mutation_type(self):
    #     for rec in self:
    #         if rec.picking_id.inbound_order_id:
    #             rec.customs_mutation_type = "inbound"
    #         elif rec.picking_id.outbound_order_id:
    #             rec.customs_mutation_type = "outbound"

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
        picking_env = self.env["stock.picking"].sudo()
        picking_id_list = [vals.get("picking_id") for vals in vals_list if vals.get("picking_id")]
        picking_map = {rec.id: rec for rec in picking_env.browse(picking_id_list).exists()}
        for vals in vals_list:
            picking = picking_map.get(vals.get("picking_id"))
            if picking and picking.inbound_order_id:
                vals["customs_mutation_type"] = "inbound"
            elif picking and picking.outbound_order_id:
                vals["customs_mutation_type"] = "outbound"
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
        if self.env.context.get("skip_auto_customs_mutation_type"):
            return super().write(vals)

        vals_write = dict(vals)
        if ("hs_code" in vals_write or "customs_code" in vals_write) and "product_id" not in vals_write:
            raise UserError(_("HS Code and Customs Code are reference values and cannot be modified."))
        if vals_write.get("product_id"):
            product = self.env["product.product"].sudo().browse(vals_write["product_id"])
            vals_ref = get_reference_vals(product)
            vals_write["hs_code"] = vals_ref["hs_code"]
            vals_write["customs_code"] = vals_ref["customs_code"]
            vals_write.setdefault("origin_country", vals_ref["origin_country"])
            vals_write.setdefault("goods_value", vals_ref["goods_value"])
            vals_write.setdefault("weight", vals_ref["weight"])

        res = super().write(vals_write)
        if "picking_id" not in vals_write and "customs_mutation_type" not in vals_write:
            return res
        for rec in self:
            mutation_type = False
            if rec.picking_id.inbound_order_id:
                mutation_type = "inbound"
            elif rec.picking_id.outbound_order_id:
                mutation_type = "outbound"
            if not mutation_type:
                continue
            if rec.customs_mutation_type != mutation_type:
                rec.with_context(skip_auto_customs_mutation_type=True).write({"customs_mutation_type": mutation_type})
        return res
