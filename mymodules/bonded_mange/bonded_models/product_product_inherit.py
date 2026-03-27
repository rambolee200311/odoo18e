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
    ], string="Customs Status", index=True, tracking=True,required=True,default="vrij")



    def write(self, vals):
        #属性值修改日志
        audit_field_list = self.getCustomsAuditFieldList()
        hit_field_list = [x for x in audit_field_list if x in vals]
        old_value_map = {}
        if hit_field_list:
            for rec in self:
                old_value_map[rec.id] = {f: rec.getAuditValueText(rec, f) for f in hit_field_list}
        res = super().write(vals)
        if hit_field_list:
            self.actionCreateCustomsAuditLog(old_value_map, action_type="manual")

        # 海关状态联动mrn状态
        if vals.get("customs_status"):
            quant_ids = self.env["stock.quant"].sudo().search([("product_id", "in", self.ids)]).ids
            for quant in self.env["stock.quant"].browse(quant_ids):
                quant.write({"customs_status": vals["customs_status"]})
        return res

    def getCustomsAuditFieldList(self):
        return ["customs_status", "hs_code", "customs_code", "origin_country", "goods_value"]

    def getAuditValueText(self, rec, field_name):
        field = rec._fields[field_name]
        value = rec[field_name]
        if field.type == "many2one":
            return value.display_name if value else ""
        return "" if value in (False, None) else str(value)

    def actionCreateCustomsAuditLog(self, old_value_map, action_type="manual", remark=""):
        log_env = self.env["bonded.customs.mrn.audit.log"]
        vals_list = []
        for rec in self:
            for field_name in rec.getCustomsAuditFieldList():
                old_text = old_value_map.get(rec.id, {}).get(field_name, "")
                new_text = rec.getAuditValueText(rec, field_name)
                if old_text == new_text:
                    continue
                vals_list.append({
                    "model_name": rec._name,
                    "res_id": rec.id,
                    "field_name": field_name,
                    "old_value": old_text,
                    "new_value": new_text,
                    "product_id": rec.id,
                    "action_type": action_type,
                    "operation_remark": remark or "customs field changed",
                })
        if vals_list:
            log_env.create(vals_list)