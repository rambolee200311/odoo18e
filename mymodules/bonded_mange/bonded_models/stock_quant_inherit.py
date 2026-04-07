from odoo import api, fields, models, _
from odoo.exceptions import UserError

def get_reference_vals(product):
    return {
        "origin_country": product.origin_country.id or False,
        "goods_value": product.goods_value or 0.0,
        "hs_code": product.hs_code or False,
        "weight": product.weight or 0.0,
        "customs_code": product.customs_code or False,
    }


class StockQuant(models.Model):
    _inherit = "stock.quant"

    origin_country = fields.Many2one("res.country", string="Country of Origin", tracking=True, index=True)
    goods_value = fields.Monetary(
        string='Goods Value',
        currency_field='currency_id',
        tracking=True)
    hs_code = fields.Char(string="HS Code", tracking=True, readonly=True, index=True)
    weight = fields.Float(string="Weight", tracking=True)
    customs_code = fields.Char(string="Customs Code", tracking=True, readonly=True, index=True)
    unique_identifier = fields.Char(string='Unique Identifier', copy=False, index=True)
    file_identifier = fields.Char(string='File Identifier', copy=False, index=True, readonly=True)
    currency_id = fields.Many2one(
        'res.currency',
        string='Currency',
        default=lambda self: self.env.company.currency_id)

    customs_status = fields.Selection([
        ("vrij", "Vrij"),
        ("rto", "Return to Origin"),
        ("entrepot", "Bonded Warehouse"),
        ("accijns", "Excise Goods"),
        ("ivv", "Import/Export/Transit & Equivalent"),
        ("bonded", "Bonded"),
        ("non_bonded", "Free / Non-bonded"),
    ], string="Customs Status", index=True, tracking=True,required=True,default="vrij")
    mrn_id = fields.Many2one("bonded.mrn.master", string="MRN", index=True, copy=False, tracking=True)
    mrn_status = fields.Selection([
    ("pending_declaration", "Pending Declaration"),
    ("declared", "Declared"),
    ("cleared", "Cleared"),
    ("status_changed", "Status Changed"),
    ("exception", "Exception"),
    ], string="MRN Status", default="pending_declaration",tracking=True, copy=False, index=True)

    t1_document_number = fields.Char(string="T1 Document Number", index=True, copy=False)
    t1_status = fields.Selection([
        ("open", "Open"),
        ("closed", "Closed"),
    ], string="T1 Status", default="open", tracking=True, index=True)

    t1_closed_date = fields.Date(string="T1 Closed Date", tracking=True)

    def update_customs_status(self):
        for rec in self:
            if rec.mrn_id:
                rec.customs_status = rec.mrn_id.customs_status
            else:rec.customs_status = "vrij"



    @api.model_create_multi
    def create(self, vals_list):
        #唯一标识号管理,档案编号
        lot_env = self.env['stock.lot']
        for vals in vals_list:
            if vals.get('lot_id'):
                lot = lot_env.sudo().browse(vals['lot_id'])
                if lot.unique_identifier and not vals.get('unique_identifier'):
                    vals['unique_identifier'] = lot.unique_identifier
                if lot.file_identifier and not vals.get('file_identifier'):
                    vals['file_identifier'] = lot.file_identifier
            #  产品
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
        vals_write = dict(vals)
        if vals_write.get('lot_id'):
            lot = self.env['stock.lot'].sudo().browse(vals_write['lot_id'])
            if lot.unique_identifier and not vals_write.get('unique_identifier'):
                vals_write['unique_identifier'] = lot.unique_identifier
            if lot.file_identifier and not vals_write.get('file_identifier'):
                vals_write['file_identifier'] = lot.file_identifier


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