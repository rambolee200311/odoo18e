from odoo import api, fields, models, _
from odoo.exceptions import ValidationError

class WaybillContainerInherit(models.Model):
    _inherit = "world.depot.waybill.container"
    _rec_name = 'container_number'

    inbound_order_id = fields.Many2one("world.depot.inbound.order", string="Inbound Order", copy=False, readonly=True)

    def action_create_inbound_order(self):
        inbound_model = self.env["world.depot.inbound.order"]
        inbound_order_ids = []

        for rec in self:
            if not rec.waybill_id:
                raise ValidationError(_("Waybill is required."))
            if rec.waybill_id.state != 'confirm':
                raise ValidationError(_("Waybill must be confirmed before creating an inbound order."))
            if not rec.waybill_id.project:
                raise ValidationError(_("Project is required before creating an inbound order."))
            if not rec.container_number:
                raise ValidationError(_("Container number is required."))

            waybill = rec.waybill_id
            bl_no = waybill.bl_number or waybill.hbl_number or waybill.obl_number

            inbound_order = inbound_model.sudo().search([
                ("project", "=", waybill.project.id),
                ("cntr_no", "=", rec.container_number),
                ("bl_no", "=", bl_no),
                ("state", "!=", "cancel"),
            ], limit=1)

            if not inbound_order:
                inbound_order = inbound_model.create({
                    "project": waybill.project.id,
                    "cntr_no": rec.container_number,
                    "bl_no": bl_no,
                    "waybill_id": rec.waybill_id.id,
                })
            if rec.inbound_order_id != inbound_order:
                rec.write({
                    "inbound_order_id": inbound_order.id,
                })
            inbound_order_ids.append(inbound_order.id)

        if len(inbound_order_ids) == 1:
            return {
                "type": "ir.actions.act_window",
                "name": _("Inbound Order"),
                "res_model": "world.depot.inbound.order",
                "res_id": inbound_order_ids[0],
                "view_mode": "form",
                "views": [(False, "form")],
                "target": "current",
            }

        return {
            "type": "ir.actions.act_window",
            "name": _("Inbound Orders"),
            "res_model": "world.depot.inbound.order",
            "view_mode": "list,form",
            "views": [(False, "list"), (False, "form")],
            "domain": [("id", "in", inbound_order_ids)],
            "target": "current",
        }