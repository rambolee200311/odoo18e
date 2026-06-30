from odoo.exceptions import UserError
from odoo import _, api, fields, models

class PortbaseWaybillImportWizard(models.TransientModel):
    _name = "portbase.waybill.import.wizard"
    _description = "portbase.waybill.import.wizard"
    _order = "id desc"

    project_id = fields.Many2one("project.project", string="Project", required=True, index=True)
    bl_number = fields.Char(string="BL Number", required=True, index=True)
    container_number = fields.Char(string="Container Number", required=True, index=True)
    tracking_id = fields.Char(string="Tracking Id", readonly=True, copy=False)
    waybill_id = fields.Many2one("world.depot.waybill", string="Waybill", readonly=True, copy=False)
    sync_message = fields.Char(string="Sync Message", readonly=True, copy=False)

    def action_subscribe_and_sync(self):
        self.ensure_one()

        env_waybill = self.env["world.depot.waybill"]
        tracked_item, tracking_id = env_waybill.fetch_portbase_by_bl_and_container(self.bl_number, self.container_number)
        waybill = env_waybill.upsert_waybill_from_portbase(tracked_item, self.project_id.id, self.bl_number, tracking_id)
        env_waybill.sync_waybill_full_containers_from_portbase(waybill, tracked_item, tracking_id)

        message = _("Sync success, bl=%s tracking id=%s") % (self.bl_number, tracking_id)
        self.write({"tracking_id": tracking_id, "waybill_id": waybill.id, "sync_message": message})

        return {
            "type": "ir.actions.act_window",
            "name": _("Waybill"),
            "res_model": "world.depot.waybill",
            "view_mode": "form",
            "res_id": waybill.id,
            "target": "current",
        }