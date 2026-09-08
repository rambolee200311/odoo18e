# © 2024 Wukong Digital. License LGPL-3.
import json

from odoo import api, fields, models


FAILURE_STAGES = [
    ("INPUT_STRATEGY", "Input Strategy"),
    ("PDF_PREPROCESS", "PDF Preprocess"),
    ("PAGE_PROVIDER_REQUEST", "Page Provider Request"),
    ("PAGE_PROVIDER_RESPONSE", "Page Provider Response"),
    ("PAGE_SCHEMA_VALIDATION", "Page Schema Validation"),
    ("DOCUMENT_NORMALIZATION", "Document Normalization"),
    ("CANONICAL_VALIDATION", "Canonical Validation"),
    ("MAPPING", "Mapping"),
    ("PERSISTENCE", "Persistence"),
    ("OTHER", "Other"),
]


class VendorInvoiceImportProviderCall(models.Model):
    _name = "vendor.invoice.import.provider.call"
    _description = "AI Parse Provider Call"
    _order = "parse_attempt_id, call_sequence, id"

    parse_attempt_id = fields.Many2one(
        "vendor.invoice.import.parse.attempt",
        required=True,
        ondelete="cascade",
        index=True,
    )
    company_id = fields.Many2one(
        "res.company",
        related="parse_attempt_id.task_id.company_id",
        store=True,
        readonly=True,
        index=True,
    )
    page_artifact_id = fields.Many2one(
        "vendor.invoice.import.page.artifact",
        ondelete="set null",
        readonly=True,
        index=True,
    )
    page_artifact_ids = fields.Many2many(
        "vendor.invoice.import.page.artifact",
        "vendor_invoice_provider_call_page_rel",
        "provider_call_id",
        "page_artifact_id",
        string="Page Artifacts",
        readonly=True,
    )
    input_page_count = fields.Integer(readonly=True)
    input_mode = fields.Selection(
        [
            ("rendered_images", "Rendered Images"),
            ("native_pdf", "Native PDF"),
        ],
        readonly=True,
    )
    input_document_type = fields.Char(readonly=True)
    rendered_image_count = fields.Integer(readonly=True)
    returned_page_count = fields.Integer(readonly=True)
    failure_page_no = fields.Integer(readonly=True)
    call_sequence = fields.Integer(required=True, readonly=True)
    retry_index = fields.Integer(required=True, readonly=True)
    provider_snapshot = fields.Char(required=True, readonly=True)
    model_snapshot = fields.Char(required=True, readonly=True)
    effective_prompt_snapshot = fields.Json(
        readonly=True,
        groups="ai_vendor_invoice.group_config_manager",
    )
    effective_prompt_display = fields.Text(
        string="Effective Prompt",
        compute="_compute_effective_prompt_display",
        groups="ai_vendor_invoice.group_config_manager",
    )
    request_started_at = fields.Datetime(readonly=True, index=True)
    response_received_at = fields.Datetime(readonly=True)
    http_status = fields.Integer(readonly=True)
    outcome = fields.Selection(
        [
            ("pending", "Pending"),
            ("success", "Success"),
            ("no_response", "No Response"),
            ("response_invalid", "Response Invalid"),
            ("failed", "Failed"),
        ],
        required=True,
        default="pending",
        readonly=True,
        index=True,
    )
    raw_response_attachment_id = fields.Many2one(
        "ir.attachment",
        ondelete="set null",
        readonly=True,
        groups="ai_vendor_invoice.group_config_manager",
    )
    page_extraction_result = fields.Json(readonly=True)
    page_extraction_status = fields.Selection(
        [
            ("generated", "GENERATED"),
            ("not_generated", "NOT_GENERATED"),
            ("failed_before_stage", "FAILED_BEFORE_STAGE"),
        ],
        string="Page Extraction Status",
        compute="_compute_page_extraction_status",
    )
    validation_status = fields.Selection(
        [
            ("not_run", "Not Run"),
            ("pass", "Pass"),
            ("fail", "Fail"),
        ],
        required=True,
        default="not_run",
        readonly=True,
    )
    failure_stage = fields.Selection(FAILURE_STAGES, readonly=True, index=True)
    safe_error_summary = fields.Char(readonly=True)

    @api.depends("effective_prompt_snapshot")
    def _compute_effective_prompt_display(self):
        for call in self:
            call.effective_prompt_display = (
                json.dumps(call.effective_prompt_snapshot, indent=2, ensure_ascii=True)
                if call.effective_prompt_snapshot
                else False
            )

    @api.depends("page_extraction_result", "validation_status", "outcome")
    def _compute_page_extraction_status(self):
        for call in self:
            if call.page_extraction_result and call.validation_status == "pass":
                call.page_extraction_status = "generated"
            elif call.validation_status == "fail" or call.outcome in (
                "failed",
                "no_response",
                "response_invalid",
            ):
                call.page_extraction_status = "failed_before_stage"
            else:
                call.page_extraction_status = "not_generated"

    _sql_constraints = [
        (
            "attempt_call_sequence_unique",
            "unique(parse_attempt_id, call_sequence)",
            "Provider call sequence must be unique per parse attempt.",
        ),
        (
            "call_sequence_positive",
            "check(call_sequence > 0)",
            "Provider call sequence must be positive.",
        ),
        (
            "retry_index_nonnegative",
            "check(retry_index >= 0)",
            "Provider retry index cannot be negative.",
        ),
    ]
