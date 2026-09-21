# odoo18e/mymodules/wd_iffm/models/portbase_webhook_log.py
from odoo import fields, models


class PortbaseWebhookLog(models.Model):
    _name = "portbase.webhook.log"
    _description = "portbase.webhook.log"
    _order = "id desc"

    event_id = fields.Char(string="Event Id", index=True, copy=False)
    event_type = fields.Char(string="Event Type", index=True, copy=False)
    tracking_id = fields.Char(string="Tracking Id", index=True, copy=False)
    bl_number = fields.Char(string="BL Number", index=True, copy=False)
    reference_number = fields.Char(string="Reference Number", index=True, copy=False)
    request_ip = fields.Char(string="Request Ip", copy=False)
    request_headers = fields.Text(string="Request Headers", copy=False)
    raw_payload = fields.Text(string="Raw Payload", required=True, copy=False)
    process_status = fields.Selection([("new", "New"), ("done", "Done"), ("error", "Error")], string="Process Status", default="new", index=True, tracking=True, copy=False)
    process_message = fields.Text(string="Process Message", copy=False)
    received_at = fields.Datetime(string="Received At", default=fields.Datetime.now, required=True, index=True, copy=False)
