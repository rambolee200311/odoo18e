from odoo import api, models

class StockQuant(models.Model):
    _inherit = "stock.quant"

    def getMrnStatusByCustomsStatus(self, customs_status):
        if customs_status in ("bonded", "entrepot"):
            return "pending_declaration"   # 待申报
        if customs_status in ("vrij", "non_bonded"):
            return "cleared"               # 已清关
        if customs_status in ("rto", "ivv", "ivv_equivalent"):
            return "declared"              # 已申报
        if customs_status == "accijns":
            return "exception"             # 异常
        return "status_changed"            # 状态变更

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("customs_status") and not vals.get("mrn_status"):
                vals["mrn_status"] = self.getMrnStatusByCustomsStatus(vals["customs_status"])
        return super().create(vals_list)

    def write(self, vals):
        vals_write = dict(vals)
        old_status_map = {}
        if "customs_status" in vals_write:
            for rec in self:
                old_status_map[rec.id] = rec.customs_status
            if "mrn_status" not in vals_write:
                vals_write["mrn_status"] = self.getMrnStatusByCustomsStatus(vals_write["customs_status"])

        res = super().write(vals_write)

        if "customs_status" in vals_write:
            self.actionCreateCustomsMrnAuditLog(old_status_map, action_type="manual")
        return res

    @api.onchange("customs_status")
    def onchangeCustomsStatusSetMrnStatus(self):
        for rec in self:
            if rec.customs_status:
                rec.mrn_status = rec.getMrnStatusByCustomsStatus(rec.customs_status)

    def actionCreateCustomsMrnAuditLog(self, old_status_map, action_type="manual"):
        log_model = self.env["bonded.customs.mrn.audit.log"]
        vals_list = []
        for rec in self:
            old_status = old_status_map.get(rec.id)
            if old_status == rec.customs_status:
                continue
            vals_list.append({
                "model_name": "stock.quant",
                "res_id": rec.id,
                "field_name": "customs_status",
                "old_value": old_status or "",
                "new_value": rec.customs_status or "",
                "customs_status_old": old_status or False,
                "customs_status_new": rec.customs_status or False,
                "mrn_status_old": self.getMrnStatusByCustomsStatus(old_status) if old_status else False,
                "mrn_status_new": rec.mrn_status or False,
                "mrn_code": rec.mrn_code or False,
                "quant_id": rec.id,
                "product_id": rec.product_id.id,
                "action_type": action_type,
                "operation_remark": "customs_status changed -> mrn_status auto mapped",
            })
        if vals_list:
            log_model.create(vals_list)
