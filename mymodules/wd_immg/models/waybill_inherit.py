from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError


class WaybillInherit(models.Model):
    _inherit = "world.depot.waybill"

    search_bl_hbl = fields.Char(string="BL / HBL No", store=False)
    obl_number = fields.Char(string="OBL No")
    quotation_id = fields.Many2one("charge.quotation", related='project.quotation_id',store=True,string="Quotation", index=True, tracking=True)
    container_qty = fields.Integer(string="Container Qty", tracking=True)

    handover_id = fields.Many2one("operation.order.handover", string="Handover")
    clearance_id = fields.Many2one("operation.order.clearance", string="Clearance")


    #货到港信息
    arrival_confirm_user_id = fields.Many2one("res.users", string="Arrival Confirm User", tracking=True, copy=False,
                                              readonly=True, index=True)
    arrival_confirm_time = fields.Datetime(string="Arrival Confirm Time", tracking=True, copy=False, readonly=True)
    is_arrived = fields.Boolean(string="Is Arrived")

    def action_open_arrival_wizard(self):
        for rec in self:
            if rec.state != "confirm":
                raise ValidationError(_("Only waybills in confirm status can confirm cargo arrival"))
        return {
            "type": "ir.actions.act_window",
            "name": _("Cargo Arrival Confirmation"),
            "res_model": "waybill.arrival.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {
                "default_waybill_id": self.id,
                "default_actual_arrival_date": fields.Date.context_today(self),
            }
        }


    @api.constrains('other_docs_ids')
    def constrain_required_documents(self):
        if self.env.context.get("skip_bl_required"):
            return
        for rec in self:
            bl_lines = rec.other_docs_ids.filtered(lambda l: l.bill_doc_type == 'bl' and l.file)
            if not bl_lines:
                raise ValidationError(_("BL file is required."))

    def name_get(self):
        res = []
        for rec in self:
            parts = []
            if rec.bl_number:
                parts.append(f"BL:{rec.bl_number}")
            if rec.hbl_number:
                parts.append(f"HBL:{rec.hbl_number}")
            res.append((rec.id, " / ".join(parts)))
        return res

    @api.model
    def name_search(self, name="", args=None, operator="ilike", limit=100):
        args = args or []
        domain = args
        if name:
            domain = ["|",
                      ("bl_number", operator, name),
                      ("hbl_number", operator, name)
                      ] + args
        records = self.search(domain, limit=limit)
        return records.name_get()

    @api.onchange("container_ids")
    def onchange_container_ids(self):
        for rec in self:
            rec.container_qty = len(rec.container_ids)

    def action_create_handover(self):
        for rec in self:
            if rec.state != "confirm":
                raise UserError(_("Please change the status to confirm"))

            attachment_lines = [(0, 0, {
                "doc_type": ln.bill_doc_type,
                "remark": ln.description,
                "file": ln.file,
                "name": ln.filename,
            }) for ln in rec.other_docs_ids]



            charge_lines = [(0, 0, {
                "charge_item_id": ln.charge_item_id.id,
                "charge_origin_type": 'quotation',
                "unit_price": ln.unit_price,
            })for ln in rec.quotation_id.quotation_thc_lines]

            handover_id = rec.env['operation.order.handover'].sudo().create({
                'waybill_id': rec.id,
                'project_id': rec.project.id,
                'shipping_line_id': rec.shipping.   id,
                'container_qty': rec.container_qty,
                "attachment_line_ids": attachment_lines,
                "charge_line_ids": charge_lines,
            })
            rec.handover_id = handover_id.id
            return {
                "type": "ir.actions.act_window",
                "name": "Handover",
                "res_model": "operation.order.handover",
                "views": [(self.env.ref("wd_immg.view_operation_order_handover_form").id, "form")],
                "view_mode": "form",
                "res_id": handover_id.id,
                "target": "current",
            }

    def action_create_clearance(self):
        for rec in self:
            if rec.state != "confirm":
                raise UserError(_("Please change the status to confirm"))

            attachment_lines = [(0, 0, {
                "doc_type": ln.bill_doc_type,
                "remark": ln.description,
                "file": ln.file,
                "name": ln.filename,
            }) for ln in rec.other_docs_ids]

            charge_lines = [(0, 0, {
                "charge_item_id": ln.charge_item_id.id,
                "charge_origin_type": 'quotation',
                "unit_price": ln.unit_price,
            }) for ln in rec.quotation_id.quotation_customs_lines]

            clearance_id = rec.env['operation.order.clearance'].sudo().create({
                'waybill_id': rec.id,
                'project_id': rec.project.id,
                'shipping_line_id': rec.shipping.id,
                'handover_id': rec.handover_id.id,
                'container_qty': rec.container_qty,
                "attachment_line_ids": attachment_lines,
                "charge_line_ids": charge_lines,
            })
            rec.clearance_id = clearance_id.id
            return {
                "type": "ir.actions.act_window",
                "name": "Clearance",
                "res_model": "operation.order.clearance",
                "views": [(self.env.ref("wd_immg.operation_order_clearance_form_view").id, "form")],
                "view_mode": "form",
                "res_id": clearance_id.id,
                "target": "current",
            }