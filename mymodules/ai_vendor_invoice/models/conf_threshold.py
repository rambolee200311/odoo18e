# © 2024 Wukong Digital. License LGPL-3.
from odoo import fields, models


class WdConfidenceThreshold(models.Model):
    _name = "wd.confidence.threshold"
    _description = "Confidence Score Thresholds"
    _rec_name = "name"

    name = fields.Char(string="Config Name", required=True, default="Default")

    # Global threshold below which the field is highlighted yellow in the UI.
    global_threshold = fields.Float(
        string="Global Threshold",
        default=0.7,
        digits=(5, 4),
    )

    # Critical-field threshold below which the field is highlighted red.
    critical_threshold = fields.Float(
        string="Critical Threshold",
        default=0.9,
        digits=(5, 4),
    )

    # Comma-separated list of canonical header/line field names considered critical.
    critical_fields = fields.Char(
        string="Critical Fields",
        default="invoice_number,invoice_date,total_amount",
        help="Comma-separated canonical field names treated as critical.",
    )
