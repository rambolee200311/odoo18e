# © 2024 Wukong Digital. License LGPL-3.
# T-017: api_key field is restricted to group_config_manager; NEVER log, expose via
#         RPC, error_message, raw attachment, or Sentry.
from odoo import fields, models


class WdAiProviderConfig(models.Model):
    _name = "wd.ai.provider.config"
    _description = "AI Provider Configuration"
    _order = "sequence, id"

    name = fields.Char(string="Provider Name", required=True)
    sequence = fields.Integer(string="Sequence", default=10)
    active = fields.Boolean(string="Active", default=True)

    api_base_url = fields.Char(string="API Base URL", required=True)

    # T-017: api_key restricted to Config Manager group; adapter reads via sudo().
    api_key = fields.Char(
        string="API Key",
        groups="ai_vendor_invoice.group_config_manager",
    )

    model_name = fields.Char(string="Model Name", required=True)

    document_input_mode = fields.Selection(
        [
            ("rendered_images", "Rendered Images"),
            ("native_pdf", "Native PDF"),
        ],
        string="Document Input Mode",
        required=True,
        default="rendered_images",
        help="Transport representation sent to the configured AI provider.",
    )

    max_internal_retry = fields.Integer(
        string="Max Internal Retry",
        default=3,
    )

    http_timeout = fields.Integer(
        string="HTTP Timeout (s)",
        default=60,
    )
