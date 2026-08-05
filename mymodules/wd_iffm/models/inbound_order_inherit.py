from odoo import api, fields, models, _

class InboundOrderInherit(models.Model):
    _inherit = "world.depot.inbound.order"


    waybill_id = fields.Many2one("world.depot.waybill", string="Waybill", copy=False, readonly=True)



class InboundOrderProductsOfPalletInherit(models.Model):
    _inherit = "world.depot.inbound.order.products.pallet"

    weight = fields.Float(string='Weight (kg)', help='Weight of the product in kilograms', )

    @api.onchange("product_id")
    def onchange_product_id_fill_weight(self):
        for rec in self:
            rec.weight = rec.product_id.weight if rec.product_id else 0.0

    @api.model_create_multi
    def create(self, vals_list):
        product_model = self.env["product.product"]
        for vals in vals_list:
            product_id = vals.get("product_id")
            if not product_id:
                continue

            product = product_model.sudo().browse(product_id)
            if not vals.get("weight"):
                vals["weight"] = product.weight or 0.0

        records = super().create(vals_list)
        for rec in records:
            if rec.product_id and not rec.product_id.weight and rec.weight > 0:
                rec.product_id.write({
                    "weight": rec.weight,
                })
        return records

    def write(self, vals):
        if vals.get("product_id") and not vals.get("weight"):
            product = self.env["product.product"].sudo().browse(vals["product_id"])
            vals = dict(vals)
            vals["weight"] = product.weight or 0.0

        result = super().write(vals)

        if "weight" in vals:
            for rec in self:
                if rec.product_id and not rec.product_id.weight and rec.weight > 0:
                    rec.product_id.write({
                        "weight": rec.weight,
                    })
        return result