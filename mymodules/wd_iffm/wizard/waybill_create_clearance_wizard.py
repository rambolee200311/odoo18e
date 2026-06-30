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
    from_workbench = fields.Boolean(string="From Workbench",
                                    default=lambda self: bool(self.env.context.get("from_workbench")))

    @api.depends("waybill_id")
    def _compute_available_container_ids(self):
        env_clearance = self.env["operation.order.clearance"]
        for wizard in self:
            if not wizard.waybill_id:
                wizard.available_container_ids = [(6, 0, [])]
                continue
            clearances = env_clearance.sudo().search([
                ("waybill_id", "=", wizard.waybill_id.id),
                ("state", "!=", "cancelled"),

            ])
            used_ids = clearances.mapped("clearance_container_ids").ids
            available = wizard.waybill_id.container_ids.filtered(lambda rec: rec.id not in used_ids)
            wizard.available_container_ids = [(6, 0, available.ids)]

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        waybill_id = self.env.context.get("default_waybill_id")
        if not waybill_id and self.env.context.get("active_model") == "world.depot.waybill":
            waybill_id = self.env.context.get("active_id")
        if not waybill_id:
            return res

        waybill = self.env["world.depot.waybill"].sudo().browse(waybill_id)
        if not waybill.exists():
            return res

        res["waybill_id"] = waybill.id
        clearances = self.env["operation.order.clearance"].sudo().search([
            ("waybill_id", "=", waybill.id),

            ("state", "!=", "cancelled"),
        ])
        used_ids = clearances.mapped("clearance_container_ids").ids
        available_ids = waybill.container_ids.filtered(lambda rec: rec.id not in used_ids).ids
        res["container_ids"] = [(6, 0, available_ids)]
        return res

    def create_main_clearance_record(self):
        self.ensure_one()
        waybill = self.waybill_id
        env_clearance = self.env["operation.order.clearance"]

        if waybill.state != "confirm":
            raise UserError(_("Please change the waybill status to confirm first."))
        if not self.container_ids:
            raise UserError(_("Please select at least one container."))

        main_clearance = env_clearance.sudo().search([
            ("waybill_id", "=", waybill.id),
            ("parent_id", "=", False),
            ("state", "!=", "cancelled"),
        ], limit=1)
        if main_clearance:
            raise UserError(_("Main clearance already exists."))

        clearances = env_clearance.sudo().search([
            ("waybill_id", "=", waybill.id),
            ("state", "!=", "cancelled"),
        ])
        used_ids = set(clearances.mapped("clearance_container_ids").ids)
        selected_ids = set(self.container_ids.ids)
        duplicated_ids = selected_ids & used_ids
        if duplicated_ids:
            duplicated = self.env["world.depot.waybill.container"].sudo().browse(list(duplicated_ids))
            nums = ", ".join(duplicated.mapped("container_number"))
            raise UserError(_("These containers are already in clearance orders: %s") % nums)

        attachment_lines = [
            (0, 0, {"doc_type": rec.bill_doc_type, "remark": rec.description, "file": rec.file, "name": rec.filename})
            for rec in waybill.other_docs_ids]
        quotation = waybill.quotation_id
        charge_lines = [(0, 0, {"charge_item_id": rec.charge_item_id.id, "charge_origin_type": "quotation",
                                "unit_price": rec.unit_price,"is_fixed_fee": rec.is_fixed_fee,}) for rec in
                        quotation.quotation_customs_lines] if quotation else []

        clearance = env_clearance.create({
            "waybill_id": waybill.id,
            "project_id": waybill.project.id if waybill.project else False,
            "shipping_line_id": waybill.shipping.id if waybill.shipping else False,
            "handover_id": waybill.handover_id.id if waybill.handover_id else False,
            "container_qty": len(self.container_ids),
            "clearance_container_ids": [(6, 0, self.container_ids.ids)],
            "attachment_line_ids": attachment_lines,
            "charge_line_ids": charge_lines,
        })
        waybill.write({"clearance_id": clearance.id})
        return clearance

    def action_confirm(self):
        self.ensure_one()
        clearance = self.create_main_clearance_record()
        self.env["operation.workbench.card"].action_sync_cards_by_waybill(self.waybill_id.id)
        return {
            "type": "ir.actions.act_window",
            "name": "Clearance",
            "res_model": "operation.order.clearance",
            "views": [(self.env.ref("wd_iffm.operation_order_clearance_form_view").id, "form")],
            "view_mode": "form",
            "res_id": clearance.id,
            "target": "current",
        }

    def action_confirm_workbench(self):
        self.ensure_one()
        self.create_main_clearance_record()
        self.env["operation.workbench.card"].action_sync_cards_by_waybill(self.waybill_id.id)
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Success"),
                "message": _("Main clearance created successfully."),
                "type": "success",
                "sticky": False,
                "next": {"type": "ir.actions.act_window_close"},
            },
        }