from odoo import api, models

class StockQuant(models.Model):
    _inherit = "stock.quant"

    @api.model_create_multi
    def create(self, vals_list):
        mrn_model = self.env["bonded.mrn.master"]
        for vals in vals_list:
            if vals.get("mrn_id"):
                mrn = mrn_model.sudo().browse(vals["mrn_id"])
                vals.setdefault("mrn_status", mrn.mrn_status)
                vals.setdefault("customs_status", mrn.customs_status)
                vals.setdefault("t1_document_number", mrn.t1_document_number)
                vals.setdefault("t1_status", mrn.t1_status)
                vals.setdefault("t1_closed_date", mrn.t1_closed_date)
        return super().create(vals_list)

    def write(self, vals):
        vals_write = dict(vals)
        mrn_model = self.env["bonded.mrn.master"]
        if "mrn_id" in vals_write and not vals_write["mrn_id"]:
            vals_write.update({

                "mrn_status": False,
                "t1_document_number": False,
                "t1_status": "open",
                "t1_closed_date": False,
            })

        if vals_write.get("mrn_id"):
            mrn = self.env["bonded.mrn.master"].sudo().browse(vals_write["mrn_id"])
            vals_write.setdefault("mrn_status", mrn.mrn_status)
            vals_write.setdefault("customs_status", mrn.customs_status)
            vals_write.setdefault("t1_document_number", mrn.t1_document_number)
            vals_write.setdefault("t1_status", mrn.t1_status)
            vals_write.setdefault("t1_closed_date", mrn.t1_closed_date)

        old_status_map = {}
        if "customs_status" in vals_write:
            for rec in self:
                old_status_map[rec.id] = rec.customs_status

        res = super().write(vals_write)

        if "customs_status" in vals_write:
            self.actionCreateCustomsMrnAuditLog(old_status_map, action_type="manual")
        return res



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
                "mrn_id": rec.mrn_id.id or False,
                "quant_id": rec.id,
                "product_id": rec.product_id.id,
                "action_type": action_type,
                "operation_remark": "customs_status changed -> mrn_status auto mapped",
            })
        if vals_list:
            log_model.create(vals_list)
