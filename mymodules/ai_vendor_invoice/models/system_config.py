# © 2024 Wukong Digital. License LGPL-3.
# T-026: task_timeout is the sole cross-transaction timeout baseline for cron.
import datetime

from odoo import api, fields, models


class WdSystemConfig(models.Model):
    _name = "wd.system.config"
    _description = "WD AI Vendor Invoice System Config"
    _rec_name = "name"

    name = fields.Char(string="Config Name", required=True, default="Default")

    default_product_id = fields.Many2one(
        "product.product",
        string="Default Fallback Product",
        help="Used when human_review_result has no lines.",
    )

    # Stored as integer seconds; exposed as timedelta in get_config().
    task_timeout_seconds = fields.Integer(
        string="Task Timeout (seconds)",
        default=3600,
        help="Cron timeout baseline; covers both queued and running parse states.",
    )

    cron_interval_minutes = fields.Integer(
        string="Cron Interval (minutes)",
        default=5,
    )

    queue_wait_warning_seconds = fields.Integer(
        string="Queue Wait Diagnostic Threshold (seconds)",
        default=300,
        help=(
            "Operational-only threshold for QUEUE_WAIT_EXCESSIVE. "
            "It never changes a task or attempt state."
        ),
    )

    amount_tolerance = fields.Float(
        string="Amount Tolerance",
        default=0.01,
        digits=(10, 4),
    )

    @property
    def task_timeout(self):
        """Return task_timeout_seconds as a datetime.timedelta."""
        return datetime.timedelta(seconds=self.task_timeout_seconds)

    @api.model
    def get_config(self):
        """Return singleton system config; falls back to first record or empty."""
        cfg = self.search([], limit=1)
        if not cfg:
            cfg = self.create({"name": "Default"})
        return cfg
