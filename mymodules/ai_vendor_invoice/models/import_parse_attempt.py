# © 2024 Wukong Digital. License LGPL-3.
# T-018: (task_id, sequence) must be unique at DB level.
# T-022: status queued → running only when worker actually starts.
# T-024: job_run_parse is the sole queue_job entry point (service must not with_delay directly).
from odoo import api, fields, models

from ..adapters.aibase import (
    EXTRACTION_CONTRACT_VERSION,
    PROMPT_VERSION,
)
from .provider_call import FAILURE_STAGES


class VendorInvoiceImportParseAttempt(models.Model):
    _name = "vendor.invoice.import.parse.attempt"
    _description = "AI Vendor Invoice Parse Attempt"
    _order = "task_id, sequence"

    task_id = fields.Many2one(
        "vendor.invoice.import.task",
        string="Import Task",
        required=True,
        ondelete="cascade",
        index=True,
    )
    source_pdf_attachment_id = fields.Many2one(
        related="task_id.source_pdf_attachment_id",
        string="Source PDF",
        readonly=True,
    )

    sequence = fields.Integer(
        string="Sequence",
        required=True,
    )

    provider_config_id = fields.Many2one(
        "wd.ai.provider.config",
        string="AI Provider Config",
        required=True,
    )

    prompt_version = fields.Char(
        string="Prompt Version",
        readonly=True,
    )

    extraction_contract_version = fields.Char(
        string="Extraction Contract Version",
        readonly=True,
    )

    model_name_snapshot = fields.Char(
        string="Model Name Snapshot",
        readonly=True,
    )

    started_at = fields.Datetime(
        string="Started At",
        readonly=True,
        index=True,
    )

    submitted_at = fields.Datetime(
        string="Submitted At",
        readonly=True,
        index=True,
        help="When this attempt was submitted to the asynchronous queue.",
    )

    completed_at = fields.Datetime(
        string="Completed At",
        readonly=True,
        index=True,
        help="When the worker finished this attempt.",
    )

    finished_at = fields.Datetime(
        string="Finished At",
        readonly=True,
    )

    attempt_internal_retry_count = fields.Integer(
        string="Internal Retry Count",
        default=0,
    )

    status = fields.Selection(
        selection=[
            ("queued", "Queued"),
            ("running", "Running"),
            ("success", "Success"),
            ("failed", "Failed"),
            ("superseded", "Superseded"),
            ("cancelled", "Cancelled"),
        ],
        string="Status",
        required=True,
        index=True,
        default="queued",
    )

    # last_activity_at: local-only diagnostics; NOT used for cross-transaction
    # heartbeat / timeout decisions (T-026).
    last_activity_at = fields.Datetime(
        string="Last Activity At",
        index=True,
    )

    provider_diagnostics = fields.Json(
        string="Provider Diagnostics",
        help="Non-sensitive page and transport metadata for provider diagnosis.",
    )

    failure_stage = fields.Selection(
        FAILURE_STAGES,
        string="Failure Stage",
        readonly=True,
        index=True,
        groups=(
            "ai_vendor_invoice.group_reviewer,"
            "ai_vendor_invoice.group_config_manager"
        ),
        help="Diagnostic stage only; this does not extend the business state.",
    )

    observability_status = fields.Selection(
        selection=[
            ("complete", "Complete"),
            ("partial", "Partial"),
            ("unavailable", "Unavailable"),
        ],
        string="Verification Evidence",
        required=True,
        default="unavailable",
        readonly=True,
        help="Completeness of diagnostic evidence; never a business status.",
    )

    evidence_pdf_status = fields.Selection(
        [
            ("generated", "GENERATED"),
            ("not_available_for_historical_attempt", "NOT_AVAILABLE_FOR_HISTORICAL_ATTEMPT"),
        ],
        string="PDF Evidence",
        compute="_compute_evidence_status",
    )
    evidence_page_extraction_status = fields.Selection(
        [
            ("generated", "GENERATED"),
            ("failed_before_stage", "FAILED_BEFORE_STAGE"),
            ("not_generated", "NOT_GENERATED"),
            ("not_available_for_historical_attempt", "NOT_AVAILABLE_FOR_HISTORICAL_ATTEMPT"),
        ],
        string="Page Extraction",
        compute="_compute_evidence_status",
    )
    evidence_canonical_status = fields.Selection(
        [
            ("generated", "GENERATED"),
            ("failed_before_stage", "FAILED_BEFORE_STAGE"),
            ("not_available_for_historical_attempt", "NOT_AVAILABLE_FOR_HISTORICAL_ATTEMPT"),
        ],
        string="Canonical Result",
        compute="_compute_evidence_status",
    )
    evidence_mapping_status = fields.Selection(
        [
            ("generated", "GENERATED"),
            ("failed_before_stage", "FAILED_BEFORE_STAGE"),
            ("not_available_for_historical_attempt", "NOT_AVAILABLE_FOR_HISTORICAL_ATTEMPT"),
        ],
        string="Mapping Result",
        compute="_compute_evidence_status",
    )
    failure_page_no = fields.Integer(
        string="Failure Page",
        compute="_compute_evidence_status",
    )
    failure_call_sequence = fields.Integer(
        string="Failure Provider Call",
        compute="_compute_evidence_status",
    )
    failure_explanation = fields.Char(
        string="Failure Explanation",
        compute="_compute_evidence_status",
    )

    page_artifact_ids = fields.One2many(
        "vendor.invoice.import.page.artifact",
        "parse_attempt_id",
        string="Page Artifacts",
        readonly=True,
        groups=(
            "ai_vendor_invoice.group_reviewer,"
            "ai_vendor_invoice.group_config_manager"
        ),
    )

    provider_call_ids = fields.One2many(
        "vendor.invoice.import.provider.call",
        "parse_attempt_id",
        string="Provider Calls",
        readonly=True,
        groups=(
            "ai_vendor_invoice.group_reviewer,"
            "ai_vendor_invoice.group_config_manager"
        ),
    )

    canonical_result = fields.Json(
        string="Canonical Result",
    )

    mapping_result = fields.Json(
        string="Mapping Result",
    )

    raw_response_attachment_id = fields.Many2one(
        "ir.attachment",
        string="Raw AI Response",
        ondelete="set null",
        groups="ai_vendor_invoice.group_config_manager",
    )

    error_message = fields.Text(
        string="Error Message",
        readonly=True,
    )

    error_summary = fields.Char(
        string="Error Summary",
        readonly=True,
        help="Safe, non-sensitive summary suitable for display to users.",
    )

    queue_job_id = fields.Many2one(
        "queue.job",
        string="Queue Job",
        readonly=True,
        ondelete="set null",
        index=True,
    )

    queue_diagnostic = fields.Selection(
        selection=[
            ("QUEUE_WAIT_EXCESSIVE", "QUEUE_WAIT_EXCESSIVE"),
        ],
        string="Queue Diagnostic",
        compute="_compute_queue_diagnostic",
        readonly=True,
        help="Operational diagnostic only; never changes business state.",
    )

    # ── DB constraints ────────────────────────────────────────────────────────

    _sql_constraints = [
        (
            "task_sequence_unique",
            "unique(task_id, sequence)",
            "Parse attempt sequence must be unique per task.",
        )
    ]

    @api.model_create_multi
    def create(self, vals_list):
        """Capture provider provenance once, rather than reading it later."""
        values_list = []
        for values in vals_list:
            values = dict(values)
            if values.get("provider_config_id"):
                provider = self.env["wd.ai.provider.config"].browse(
                    values["provider_config_id"]
                )
                values.setdefault("model_name_snapshot", provider.model_name)
            values.setdefault("prompt_version", PROMPT_VERSION)
            values.setdefault(
                "extraction_contract_version",
                EXTRACTION_CONTRACT_VERSION,
            )
            values.setdefault("submitted_at", fields.Datetime.now())
            values_list.append(values)
        return super().create(values_list)

    @api.depends(
        "page_artifact_ids",
        "provider_call_ids",
        "provider_call_ids.page_extraction_result",
        "provider_call_ids.validation_status",
        "provider_call_ids.failure_stage",
        "provider_call_ids.failure_page_no",
        "canonical_result",
        "mapping_result",
        "failure_stage",
    )
    def _compute_evidence_status(self):
        for attempt in self:
            artifacts = attempt.page_artifact_ids
            calls = attempt.provider_call_ids.sorted("call_sequence")
            attempt.evidence_pdf_status = (
                "generated" if artifacts else "not_available_for_historical_attempt"
            )
            successful_extractions = calls.filtered(
                lambda call: bool(call.page_extraction_result)
                and call.validation_status == "pass"
            )
            failed_calls = calls.filtered(
                lambda call: call.validation_status == "fail"
                or call.outcome in ("failed", "no_response", "response_invalid")
            )
            if successful_extractions:
                attempt.evidence_page_extraction_status = "generated"
            elif failed_calls:
                attempt.evidence_page_extraction_status = "failed_before_stage"
            elif calls:
                attempt.evidence_page_extraction_status = "not_generated"
            else:
                attempt.evidence_page_extraction_status = (
                    "not_available_for_historical_attempt"
                )
            attempt.evidence_canonical_status = (
                "generated" if attempt.canonical_result else (
                    "failed_before_stage"
                    if calls or attempt.failure_stage
                    else "not_available_for_historical_attempt"
                )
            )
            attempt.evidence_mapping_status = (
                "generated" if attempt.mapping_result else (
                    "failed_before_stage"
                    if attempt.canonical_result or calls or attempt.failure_stage
                    else "not_available_for_historical_attempt"
                )
            )
            failure_call = failed_calls[:1]
            attempt.failure_page_no = (
                (failure_call.failure_page_no or failure_call.page_artifact_id.page_no)
                if failure_call else 0
            )
            attempt.failure_call_sequence = failure_call.call_sequence if failure_call else 0
            attempt.failure_explanation = (
                "Provider call failed before PageExtractionResult was generated."
                if failure_call and not successful_extractions
                else False
            )

    # ── queue_job entry point (T-024) ─────────────────────────────────────────

    def job_run_parse(self):
        """
        queue_job delayed-task entry point.
        This ORM method is the ONLY allowed with_delay() target.
        Business logic lives in parse_service; this method is only the queue entry.
        """
        self.ensure_one()
        from ..services.parse_service import run_parse_attempt

        return run_parse_attempt(self.env, self.task_id.id, self.id)

    def action_enqueue_parse(self):
        """Queue the model method; services must not call with_delay directly."""
        self.ensure_one()
        if self.status != "queued":
            return self.queue_job_id
        # A no-delay context would execute the parse in the request and would
        # make queued/running observability untruthful.  It is for queue_job's
        # tests only and must never be used by this business entry point.
        import os
        from odoo.exceptions import UserError

        if os.getenv("QUEUE_JOB__NO_DELAY") or self.env.context.get(
            "queue_job__no_delay"
        ):
            raise UserError(
                "AI parsing requires a real queue worker; no-delay execution is disabled."
            )
        job = self.with_delay(
            description="AI Vendor Invoice Parse #%s" % self.sequence,
            identity_key="ai_vendor_invoice_parse:%s" % self.id,
            channel="root.ai_invoice",
        ).job_run_parse()
        db_job = job.db_record() if job and hasattr(job, "db_record") else self.env[
            "queue.job"
        ]
        if db_job:
            self.write({"queue_job_id": db_job.id})
        return job

    @api.depends("status", "submitted_at", "queue_job_id", "queue_job_id.state")
    def _compute_queue_diagnostic(self):
        """Expose excessive queue wait as a controlled operational signal."""
        config = self.env["wd.system.config"].get_config()
        threshold = config.queue_wait_warning_seconds
        now = fields.Datetime.to_datetime(fields.Datetime.now())
        for attempt in self:
            attempt.queue_diagnostic = False
            if (
                threshold <= 0
                or attempt.status != "queued"
                or not attempt.submitted_at
                or not attempt.queue_job_id
                or attempt.queue_job_id.state
                not in ("pending", "enqueued", "wait_dependencies")
            ):
                continue
            submitted = fields.Datetime.to_datetime(attempt.submitted_at)
            if (now - submitted).total_seconds() > threshold:
                attempt.queue_diagnostic = "QUEUE_WAIT_EXCESSIVE"
