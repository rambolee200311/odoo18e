# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError


class WaybillCreateClearanceWizard(models.TransientModel):
    _name = "waybill.create.clearance.wizard"
    _description = "Waybill Create Clearance Wizard"

    waybill_id = fields.Many2one("world.depot.waybill", string="Waybill", required=True, readonly=True)
    available_container_ids = fields.Many2many(
        "world.depot.waybill.container",
        compute="_compute_available_container_ids",
        string="Available Containers",
    )
    container_ids = fields.Many2many(
        "world.depot.waybill.container",
        "waybill_create_clearance_wizard_container_rel",
        "wizard_id",
        "container_id",
        string="Containers To Clear",
        required=True,
    )

    @api.depends("waybill_id")
    def _compute_available_container_ids(self):
        clearance_model = self.env["operation.order.clearance"]
        for wizard in self:
            if not wizard.waybill_id:
                wizard.available_container_ids = [(6, 0, [])]
                continue

            clearances = clearance_model.search([
                ("waybill_id", "=", wizard.waybill_id.id),
                ("parent_id", "=", False),
            ])
            used_ids = clearances.mapped("clearance_container_ids").ids
            available = wizard.waybill_id.container_ids.filtered(lambda c: c.id not in used_ids)
            wizard.available_container_ids = [(6, 0, available.ids)]

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        active_id = self.env.context.get("active_id")
        active_model = self.env.context.get("active_model")
        if active_model == "world.depot.waybill" and active_id:
            waybill = self.env["world.depot.waybill"].browse(active_id)
            res["waybill_id"] = waybill.id

            clearances = self.env["operation.order.clearance"].search([
                ("waybill_id", "=", waybill.id),
                ("parent_id", "=", False),
            ])
            used_ids = clearances.mapped("clearance_container_ids").ids
            available_ids = waybill.container_ids.filtered(lambda c: c.id not in used_ids).ids
            res["container_ids"] = [(6, 0, available_ids)]
        return res

    def action_confirm(self):
        self.ensure_one()
        waybill = self.waybill_id

        if waybill.state != "confirm":
            raise UserError(_("Please change the waybill status to confirm first."))
        if not self.container_ids:
            raise UserError(_("Please select at least one container."))

        clearances = self.env["operation.order.clearance"].search([
            ("waybill_id", "=", waybill.id),
            ("parent_id", "=", False),
        ])
        used_ids = set(clearances.mapped("clearance_container_ids").ids)
        selected_ids = set(self.container_ids.ids)
        duplicated_ids = selected_ids & used_ids
        if duplicated_ids:
            duplicated = self.env["world.depot.waybill.container"].browse(list(duplicated_ids))
            nums = ", ".join(duplicated.mapped("container_number"))
            raise UserError(_("These containers are already in clearance orders: %s") % nums)

        attachment_lines = [(0, 0, {
            "doc_type": ln.bill_doc_type,
            "remark": ln.description,
            "file": ln.file,
            "name": ln.filename,
        }) for ln in waybill.other_docs_ids]

        charge_lines = [(0, 0, {
            "charge_item_id": ln.charge_item_id.id,
            "charge_origin_type": "quotation",
            "unit_price": ln.unit_price,
        }) for ln in waybill.quotation_id.quotation_customs_lines]

        clearance = self.env["operation.order.clearance"].sudo().create({
            "waybill_id": waybill.id,
            "project_id": waybill.project.id,
            "shipping_line_id": waybill.shipping.id,
            "handover_id": waybill.handover_id.id,
            "container_qty": len(self.container_ids),
            "clearance_container_ids": [(6, 0, self.container_ids.ids)],
            "attachment_line_ids": attachment_lines,
            "charge_line_ids": charge_lines,
        })

        waybill.clearance_id = clearance.id

        return {
            "type": "ir.actions.act_window",
            "name": "Clearance",
            "res_model": "operation.order.clearance",
            "views": [(self.env.ref("wd_iffm.operation_order_clearance_form_view").id, "form")],
            "view_mode": "form",
            "res_id": clearance.id,
            "target": "current",
        }
