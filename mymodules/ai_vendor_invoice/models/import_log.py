# © 2024 Wukong Digital. License LGPL-3.
from odoo import fields, models


class VendorInvoiceImportLog(models.Model):
    _name = "vendor.invoice.import.log"
    _description = "AI Vendor Invoice Audit Log"
    _order = "action_datetime desc, id desc"

    task_id = fields.Many2one(
        "vendor.invoice.import.task",
        string="Import Task",
        required=True,
        ondelete="cascade",
        index=True,
    )

    parse_attempt_id = fields.Many2one(
        "vendor.invoice.import.parse.attempt",
        string="Parse Attempt",
        ondelete="set null",
    )

    action = fields.Selection(
        selection=[
            ("ai_parse", "AI Parse"),
            ("ai_re_run", "AI Re-run"),
            ("human_modify", "Human Modify"),
            ("statement_candidate_apply", "Statement Candidate Apply"),
            ("statement_confirm", "Statement Confirm"),
            ("statement_cancel", "Statement Cancel"),
            ("task_cancel", "Task Cancel"),
            ("statement_bill_created", "Statement Bill Created"),
            ("bill_create", "Bill Create"),
            ("cron_timeout", "Cron Timeout"),
        ],
        string="Action",
        required=True,
    )

    action_datetime = fields.Datetime(
        string="Action Datetime",
        required=True,
        default=fields.Datetime.now,
    )

    user_id = fields.Many2one(
        "res.users",
        string="User",
        required=True,
        default=lambda self: self.env.user,
    )

    # Only deltas/summaries stored here; never full JSON blobs (performance).
    snapshot_delta = fields.Text(
        string="Snapshot Delta",
    )
