from odoo import api, fields, models, _
from odoo.exceptions import UserError


class ProductProduct(models.Model):
    _inherit = "product.product"

    origin_country = fields.Many2one("res.country", string="Country of Origin", tracking=True, index=True)
    goods_value = fields.Monetary(
        string='Goods Value',
        currency_field='currency_id',
        tracking=True)
    hs_code = fields.Char(string="HS Code", tracking=True, index=True)
    weight = fields.Float(string="Weight", tracking=True)
    customs_code = fields.Char(string="Customs Code", tracking=True, index=True)


    currency_id = fields.Many2one(
        'res.currency',
        string='Currency',
        default=lambda self: self.env.company.currency_id)

    customs_status = fields.Selection([
        ("vrij", "Vrij"),
        ("rto", "Return to Origin"),
        ("entrepot", "Bonded Warehouse"),
        ("accijns", "Excise Goods"),
        ("ivv", "Import/Export/Transit"),
        ("bonded", "Bonded"),
        ("non_bonded", "Free / Non-bonded"),
    ], string="Customs Status", index=True, tracking=True,required=True,default="non_bonded")


    #海关状态联动mrn状态
    def write(self, vals):
        res = super().write(vals)
        if vals.get("customs_status"):
            quant_ids = self.env["stock.quant"].sudo().search([("product_id", "in", self.ids)]).ids
            for quant in self.env["stock.quant"].browse(quant_ids):
                quant.write({"customs_status": vals["customs_status"]})
        return res