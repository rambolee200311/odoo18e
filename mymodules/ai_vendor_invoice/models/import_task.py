# © 2024 Wukong Digital. License LGPL-3.
# Architecture red-line T-025: task.company_id is immutable after creation.
import base64
import hashlib

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, ValidationError


class VendorInvoiceImportTask(models.Model):
    _name = "vendor.invoice.import.task"
    _description = "AI Vendor Invoice Import Task"
    _order = "id desc"

    # ── identity ──────────────────────────────────────────────────────────────
    name = fields.Char(
        string="Task Reference",
        required=True,
        copy=False,
        default=lambda self: _("New"),
    )

    # T-025: company_id is set once at creation and must never be changed.
    company_id = fields.Many2one(
        "res.company",
        string="Company",
        required=True,
        index=True,
        default=lambda self: self.env.company,
    )

    source_pdf_attachment_id = fields.Many2one(
        "ir.attachment",
        string="Source PDF",
        required=False,
        readonly=True,
        ondelete="restrict",
    )

    source_pdf_upload = fields.Binary(
        string="Upload PDF",
        help="Upload the source vendor invoice PDF.",
    )
    source_pdf_filename = fields.Char(string="PDF Filename")
    source_pdf_checksum = fields.Char(
        string="Source PDF Checksum",
        copy=False,
        readonly=True,
        index=True,
    )

    # ── state machine ─────────────────────────────────────────────────────────
    state = fields.Selection(
        selection=[
            ("to_parse", "To Parse"),
            ("parsing", "Parsing"),
            ("awaiting_review", "Awaiting Review"),
            ("bill_generated", "Bill Generated"),
            ("error", "Error"),
            ("cancelled", "Cancelled"),
        ],
        string="State",
        required=True,
        index=True,
        default="to_parse",
    )

    # ── AI provider & attempt tracking ────────────────────────────────────────
    selected_provider_config_id = fields.Many2one(
        "wd.ai.provider.config",
        string="AI Provider",
        required=True,
    )
    synchronous_parse = fields.Boolean(
        string="Synchronous Parse",
        default=True,
        help="Run AI parsing in this request instead of submitting a queue job.",
    )

    enter_parsing_datetime = fields.Datetime(
        string="Entered Parsing At",
        index=True,
    )

    parse_display_status = fields.Selection(
        selection=[
            ("ready", "Ready to run AI"),
            ("waiting", "Waiting for AI parsing"),
            ("running", "AI parsing in progress"),
            ("completed", "Parsing complete - ready for review"),
            ("error", "Parsing error"),
            ("bill_generated", "Bill generated"),
            ("cancelled", "Cancelled"),
        ],
        string="AI Parsing Status",
        compute="_compute_parse_display_status",
    )

    current_parse_attempt_id = fields.Many2one(
        "vendor.invoice.import.parse.attempt",
        string="Current Attempt",
        ondelete="set null",
        index=True,
    )

    parse_status = fields.Selection(
        selection=[
            ("not_submitted", "Not Submitted"),
            ("queued", "Queued"),
            ("running", "Running"),
            ("completed", "Completed"),
            ("failed", "Failed"),
            ("superseded", "Superseded"),
        ],
        string="AI Parse Status",
        compute="_compute_parse_observability",
        readonly=True,
        help="Read-only status derived from the current ParseAttempt.",
    )

    parse_error_summary = fields.Char(
        string="AI Parse Error",
        compute="_compute_parse_observability",
        readonly=True,
        help="Safe, non-sensitive user-facing summary of the current parse error.",
    )
    parse_error_badge = fields.Char(
        string="Parse Error",
        compute="_compute_parse_error_badge",
    )

    queue_diagnostic = fields.Selection(
        selection=[
            ("QUEUE_WAIT_EXCESSIVE", "QUEUE_WAIT_EXCESSIVE"),
        ],
        string="Queue Diagnostic",
        compute="_compute_parse_observability",
        readonly=True,
        help="Operational diagnostic only; never changes business state.",
    )

    parse_attempt_ids = fields.One2many(
        "vendor.invoice.import.parse.attempt",
        "task_id",
        string="Parse Attempts",
    )

    statement_id = fields.Many2one(
        "vendor.invoice.statement",
        string="Human Statement",
        ondelete="restrict",
        copy=False,
    )
    statement_required = fields.Boolean(
        string="Statement Required",
        default=True,
        copy=False,
        readonly=True,
    )

    # ── review & result ───────────────────────────────────────────────────────
    # T-006 / T-007: bill_creator reads ONLY human_review_result.
    human_review_result = fields.Json(
        string="Human Review Result",
        default=dict,
    )

    human_reviewed = fields.Boolean(
        string="Human Reviewed",
        default=False,
    )

    review_warnings = fields.Json(
        string="Review Warnings",
        default=list,
    )

    # ── bill link ─────────────────────────────────────────────────────────────
    # T-005: one task → at most one vendor bill; ondelete=restrict prevents re-generation
    vendor_bill_id = fields.Many2one(
        "account.move",
        string="Vendor Bill",
        index=True,
        ondelete="restrict",
    )

    # ── audit ─────────────────────────────────────────────────────────────────
    audit_log_ids = fields.One2many(
        "vendor.invoice.import.log",
        "task_id",
        string="Audit Logs",
    )

    _sql_constraints = []

    def init(self):
        self.env.cr.execute(
            "ALTER TABLE vendor_invoice_import_task "
            "DROP CONSTRAINT IF EXISTS company_source_pdf_checksum_unique"
        )
        self.env.cr.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS
                company_source_pdf_checksum_active_unique
            ON vendor_invoice_import_task (company_id, source_pdf_checksum)
            WHERE source_pdf_checksum IS NOT NULL AND state != 'cancelled'
            """
        )
        self.env.cr.execute(
            """
            SELECT id, source_pdf_attachment_id
            FROM vendor_invoice_import_task
            WHERE source_pdf_checksum IS NULL
              AND source_pdf_attachment_id IS NOT NULL
            """
        )
        for task_id, attachment_id in self.env.cr.fetchall():
            checksum = self._checksum_for_source(
                None,
                self.env["ir.attachment"].browse(attachment_id),
            )
            if checksum:
                self.env.cr.execute(
                    """
                    UPDATE vendor_invoice_import_task
                    SET source_pdf_checksum = %s
                    WHERE id = %s
                    """,
                    (checksum, task_id),
                )

    @api.depends("state", "current_parse_attempt_id.status")
    def _compute_parse_display_status(self):
        for task in self:
            if task.state == "parsing":
                task.parse_display_status = (
                    "running"
                    if task.current_parse_attempt_id.status == "running"
                    else "waiting"
                )
            else:
                task.parse_display_status = {
                    "to_parse": "ready",
                    "awaiting_review": "completed",
                    "error": "error",
                    "bill_generated": "bill_generated",
                    "cancelled": "cancelled",
                }.get(task.state, "ready")

    @api.depends("state")
    def _compute_parse_error_badge(self):
        for task in self:
            task.parse_error_badge = "Error" if task.state == "error" else False

    # ── ORM hooks ─────────────────────────────────────────────────────────────

    @api.model_create_multi
    def create(self, vals_list):
        uploads = []
        for vals in vals_list:
            upload = vals.pop("source_pdf_upload", None)
            filename = vals.pop("source_pdf_filename", None) or "vendor_invoice.pdf"
            uploads.append((upload, filename))
            if upload and vals.get("source_pdf_attachment_id"):
                raise ValidationError(
                    _("Provide either an uploaded PDF or an existing source attachment, not both.")
                )
            if not vals.get("source_pdf_attachment_id") and not upload:
                raise ValidationError(_("Upload a vendor invoice PDF before saving the task."))
            attachment = (
                self.env["ir.attachment"].browse(vals["source_pdf_attachment_id"])
                if vals.get("source_pdf_attachment_id")
                else self.env["ir.attachment"]
            )
            vals["source_pdf_filename"] = (
                filename if upload else attachment.name or filename
            )
            vals["source_pdf_checksum"] = self._checksum_for_source(upload, attachment)
            company = self.env["res.company"].browse(
                vals.get("company_id")
            ) if vals.get("company_id") else self.env.company
            duplicate = self.search([
                ("company_id", "=", company.id),
                ("source_pdf_checksum", "=", vals["source_pdf_checksum"]),
                ("state", "!=", "cancelled"),
            ], limit=1)
            if duplicate:
                raise ValidationError(
                    _("This PDF was already imported as Task %s.") % duplicate.name
                )
            if vals.get("name", _("New")) == _("New"):
                vals["name"] = self.env["ir.sequence"].next_by_code(
                    "vendor.invoice.import.task"
                ) or _("New")
            vals.setdefault("human_review_result", {})
            vals.setdefault("review_warnings", [])
        tasks = super().create(vals_list)
        for task, (upload, filename) in zip(tasks, uploads):
            if upload and not task.source_pdf_attachment_id:
                attachment = self.env["ir.attachment"].create({
                    "name": filename,
                    "datas": upload,
                    "mimetype": "application/pdf",
                    "res_model": task._name,
                    "res_id": task.id,
                })
                task.source_pdf_attachment_id = attachment.id
            else:
                attachment = task.source_pdf_attachment_id
            if attachment.res_model != task._name or attachment.res_id != task.id:
                attachment.write({
                    "res_model": task._name,
                    "res_id": task.id,
                })
        return tasks

    @api.model
    def _checksum_for_source(self, upload, attachment):
        if upload:
            raw = base64.b64decode(upload)
        else:
            raw = attachment.raw or b""
        if not raw:
            return False
        return hashlib.sha256(raw).hexdigest()

    def write(self, vals):
        # T-025: company_id is immutable after creation.
        if "company_id" in vals:
            raise ValidationError(
                _("The company of an import task cannot be changed after creation.")
            )
        if "statement_required" in vals:
            raise ValidationError(_("Statement requirement cannot be changed."))
        return super().write(vals)

    # ── helper: sequence for next attempt ─────────────────────────────────────

    def _get_next_attempt_sequence(self):
        """Return the next integer sequence number for a new ParseAttempt."""
        self.ensure_one()
        latest = self.env["vendor.invoice.import.parse.attempt"].search(
            [("task_id", "=", self.id)],
            order="sequence desc",
            limit=1,
        )
        return (latest.sequence if latest else 0) + 1

    def action_rerun_ai(self):
        """Run a new attempt synchronously or asynchronously."""
        self.ensure_one()
        from ..services.parse_service import start_parse

        return start_parse(
            self.env,
            self.id,
            self.selected_provider_config_id.id,
            synchronous=self.synchronous_parse,
        )

    def action_open_statement(self):
        self.ensure_one()
        if not self.statement_id:
            raise ValidationError(_("This task has no human Statement."))
        return {
            "type": "ir.actions.act_window",
            "name": _("Vendor Statement"),
            "res_model": "vendor.invoice.statement",
            "view_mode": "form",
            "res_id": self.statement_id.id,
            "target": "current",
        }

    def action_open_source_pdf(self):
        self.ensure_one()
        if not self.source_pdf_attachment_id:
            raise ValidationError(_("This task has no source PDF."))
        return {
            "type": "ir.actions.act_window",
            "name": _("Source PDF"),
            "res_model": "ir.attachment",
            "view_mode": "form",
            "res_id": self.source_pdf_attachment_id.id,
            "target": "current",
        }

    def action_cancel_task(self):
        """Cancel the Task and invalidate any in-flight synchronous parse."""
        self.ensure_one()
        if self.state in ("bill_generated", "cancelled"):
            raise ValidationError(_("This Task cannot be cancelled in its current state."))
        attempt = self.current_parse_attempt_id
        if attempt and attempt.status in ("queued", "running"):
            if attempt.queue_job_id and attempt.queue_job_id.state not in (
                "done", "failed", "cancelled",
            ):
                attempt.queue_job_id.button_cancelled()
            now = fields.Datetime.now()
            attempt.write({
                "status": "cancelled",
                "finished_at": now,
                "completed_at": now,
                "error_summary": "Cancelled by the user.",
                "error_message": "Cancelled by the user.",
            })
        self.write({"state": "cancelled"})
        self.env["vendor.invoice.import.log"].create({
            "task_id": self.id,
            "parse_attempt_id": attempt.id if attempt else False,
            "action": "task_cancel",
            "snapshot_delta": "Import Task cancelled by the user.",
        })
        return True

    @api.depends(
        "state",
        "current_parse_attempt_id",
        "current_parse_attempt_id.status",
        "current_parse_attempt_id.error_summary",
        "current_parse_attempt_id.queue_diagnostic",
    )
    def _compute_parse_observability(self):
        status_map = {
            "success": "completed",
            "queued": "queued",
            "running": "running",
            "failed": "failed",
            "superseded": "superseded",
        }
        for task in self:
            attempt = task.current_parse_attempt_id
            task.parse_status = status_map.get(attempt.status, "not_submitted")
            task.parse_error_summary = attempt.error_summary if attempt else False
            task.queue_diagnostic = attempt.queue_diagnostic if attempt else False

    def action_save_review(self, review_result):
        """Persist the review result and its audit delta without creating a bill."""
        self.ensure_one()
        if not self.env.user.has_group("ai_vendor_invoice.group_reviewer"):
            raise AccessError(_("Only an invoice reviewer can save review data."))
        if self.state != "awaiting_review":
            raise ValidationError(_("Only an invoice awaiting review can be reviewed."))
        if not isinstance(review_result, dict) or not review_result:
            raise ValidationError(_("A non-empty review result is required."))
        old_result = self.human_review_result or {}
        config = self.env["wd.system.config"].get_config()
        from ..services import validation_service

        warnings = validation_service.check_amount_balance(
            review_result, self.company_id, config.amount_tolerance
        )
        self.write({
            "human_review_result": review_result,
            "human_reviewed": True,
            "review_warnings": warnings,
        })
        self.env["vendor.invoice.import.log"].create({
            "task_id": self.id,
            "parse_attempt_id": self.current_parse_attempt_id.id,
            "action": "human_modify",
            "snapshot_delta": "Human review result updated (%s top-level keys changed)."
            % len(set(old_result) ^ set(review_result)),
        })
        return True

    def action_create_statement_from_attempt(self, attempt_id, statement_payload):
        """Create the first human Statement from a current ParseAttempt candidate."""
        self.ensure_one()
        self._check_statement_command_access()
        attempt = self.env["vendor.invoice.import.parse.attempt"].browse(attempt_id)
        if not attempt.exists() or attempt.task_id != self or attempt.status != "success":
            raise ValidationError(_("Only a successful attempt of this task can create a Statement."))
        if self.statement_id:
            raise ValidationError(_("This task already has a human Statement."))
        from .statement import validate_statement_payload

        payload = validate_statement_payload(statement_payload)
        statement = self.env["vendor.invoice.statement"]._aggregate_create(
            self._statement_values(payload, attempt)
        )
        self.env["vendor.invoice.statement.line"]._aggregate_create(
            self._statement_line_values(payload, statement)
        )
        self.statement_id = statement.id
        self._log_statement_change("human_modify", attempt, "Statement created from ParseAttempt.")
        return statement

    def _create_prefilled_statement_from_canonical(self, attempt, canonical):
        """Create the editable candidate immediately after a successful parse."""
        if self.statement_id or canonical.get("is_multi_invoice"):
            return self.statement_id
        header = canonical.get("header") or {}
        value = lambda field: (header.get(field) or {}).get("value")
        supplier_name = value("supplier_raw_text")
        currency_name = value("currency_raw_text")
        supplier = self._find_supplier_partner(supplier_name)
        currency = self.env["res.currency"].search(
            ["|", ("name", "=", currency_name), ("symbol", "=", currency_name)],
            limit=1,
        ) if currency_name else self.env["res.currency"]
        payload = {
            "invoice_number": value("invoice_number"),
            "invoice_date": value("invoice_date"),
            "supplier_id": supplier.id or None,
            "supplier_name": supplier_name,
            "currency_id": currency.id or None,
            "total_amount": value("total_amount") or 0.0,
            "total_tax": value("total_tax") or 0.0,
            "subtotal": value("subtotal") or 0.0,
            "lines": [
                {
                    "description": (line.get("description") or {}).get("value"),
                    "amount": (line.get("amount") or {}).get("value"),
                    "price_unit": (line.get("amount") or {}).get("value"),
                    "tax_raw_text": (line.get("tax_raw_text") or {}).get("value"),
                    "tax_rate": (line.get("tax_rate") or {}).get("value"),
                    "tax_amount": (line.get("tax_amount") or {}).get("value"),
                    "reconciliation_clue": line.get("reconciliation_clue"),
                    "charge_details": line.get("charge_details"),
                    "reconciliation_clues": line.get("reconciliation_clues", []),
                }
                for line in canonical.get("lines", [])
            ],
        }
        statement = self.env["vendor.invoice.statement"]._aggregate_create(
            self._statement_values(payload, attempt)
        )
        self.env["vendor.invoice.statement.line"]._aggregate_create(
            self._statement_line_values(payload, statement)
        )
        self.write({"statement_id": statement.id})
        self._log_statement_change(
            "statement_candidate_apply", attempt, "AI-prefilled Statement created."
        )
        return statement

    def _find_supplier_partner(self, supplier_name):
        """Resolve a supplier by case-insensitive exact name, then unique partial match."""
        partners = self.env["res.partner"]
        if not supplier_name:
            return partners
        exact = partners.search([("active", "=", True), ("name", "=ilike", supplier_name)], limit=1)
        if exact:
            return exact
        candidates = partners.search([("active", "=", True), ("name", "ilike", supplier_name)])
        return candidates if len(candidates) == 1 else partners

    def action_apply_statement_changes(self, statement_payload):
        """Apply human edits through the aggregate boundary."""
        self.ensure_one()
        self._check_statement_command_access()
        if not self.statement_id:
            raise ValidationError(_("This task has no human Statement to edit."))
        if self.statement_id.state != "draft":
            raise ValidationError(_("Only a draft Statement can be edited."))
        from .statement import validate_statement_payload

        payload = validate_statement_payload(statement_payload)
        statement = self.statement_id
        statement._aggregate_write(self._statement_values(payload, statement.source_parse_attempt_id))
        statement.line_ids._aggregate_unlink()
        self.env["vendor.invoice.statement.line"]._aggregate_create(
            self._statement_line_values(payload, statement)
        )
        self._log_statement_change("human_modify", statement.source_parse_attempt_id, "Human Statement changed.")
        return statement

    def action_apply_ai_candidate(self, attempt_id, statement_payload):
        """Replace a Statement with an explicitly accepted current AI candidate."""
        self.ensure_one()
        self._check_statement_command_access()
        attempt = self.env["vendor.invoice.import.parse.attempt"].browse(attempt_id)
        if not attempt.exists() or attempt.task_id != self or attempt.status != "success":
            raise ValidationError(_("Only a successful current attempt can be applied."))
        if self.current_parse_attempt_id != attempt:
            raise ValidationError(_("A stale ParseAttempt cannot be applied."))
        from .statement import validate_statement_payload

        payload = validate_statement_payload(statement_payload)
        if not self.statement_id:
            return self.action_create_statement_from_attempt(attempt.id, payload)
        statement = self.statement_id
        if statement.state != "draft":
            raise ValidationError(_("Only a draft Statement can apply an AI candidate."))
        statement._aggregate_write(
            dict(self._statement_values(payload, attempt), source_parse_attempt_id=attempt.id)
        )
        statement.line_ids._aggregate_unlink()
        self.env["vendor.invoice.statement.line"]._aggregate_create(
            self._statement_line_values(payload, statement)
        )
        self._log_statement_change(
            "statement_candidate_apply", attempt, "AI candidate explicitly applied."
        )
        return statement

    def action_apply_ai_candidate_from_statement(self):
        """Apply the current AI candidate from the Statement form."""
        self.ensure_one()
        if not self.statement_id:
            raise ValidationError(_("This task has no human Statement."))
        attempt = self.statement_id.source_parse_attempt_id
        canonical = attempt.canonical_result or {}
        payload = self._statement_payload_from_canonical(canonical)
        return self.action_apply_ai_candidate(attempt.id, payload)

    def action_confirm_statement(self, statement_payload=None):
        """Persist the review, projection, and aggregate confirmation atomically."""
        self.ensure_one()
        self._check_statement_command_access()
        if statement_payload is not None:
            payload = self._statement_payload_from_review(statement_payload)
            if self.statement_id:
                self.action_apply_statement_changes(payload)
            else:
                self.action_create_statement_from_attempt(
                    self.current_parse_attempt_id.id, payload
                )
        if not self.statement_id:
            raise ValidationError(_("A human Statement is required."))
        if self.statement_id.state not in ("draft", "confirmed"):
            raise ValidationError(
                _("Only a draft or confirmed Statement can be confirmed.")
            )
        from ..services.statement_projection import (
            assert_projection_consistent,
            statement_to_human_review_result,
        )

        projection = statement_to_human_review_result(self.statement_id)
        assert_projection_consistent(self.statement_id, projection)
        self.statement_id._aggregate_write({"state": "confirmed"})
        self.write({
            "human_review_result": projection,
            "human_reviewed": True,
            "state": "awaiting_review",
        })
        self._log_statement_change(
            "statement_confirm",
            self.statement_id.source_parse_attempt_id,
            "Human Statement confirmed.",
        )
        return True

    def action_cancel_statement(self):
        """Cancel a Statement without changing the Task import lifecycle."""
        self.ensure_one()
        self._check_statement_command_access()
        statement = self.statement_id
        if not statement:
            raise ValidationError(_("A human Statement is required."))
        if statement.state not in ("draft", "confirmed"):
            raise ValidationError(_("Only a draft or confirmed Statement can be cancelled."))
        if statement.vendor_bill_id or self.vendor_bill_id:
            raise ValidationError(_("A Statement linked to a Vendor Bill cannot be cancelled."))
        statement._aggregate_write({"state": "cancelled"})
        self._log_statement_change(
            "statement_cancel",
            statement.source_parse_attempt_id,
            "Human Statement cancelled.",
        )
        return True

    def _check_statement_command_access(self):
        if not self.env.user.has_group("ai_vendor_invoice.group_reviewer"):
            raise AccessError(_("Only an invoice reviewer can modify a human Statement."))

    def _statement_values(self, payload, attempt):
        return {
            "task_id": self.id,
            "source_parse_attempt_id": attempt.id,
            "invoice_number": payload["invoice_number"],
            "invoice_date": payload.get("invoice_date"),
            "supplier_id": payload.get("supplier_id"),
            "supplier_name": payload.get("supplier_name"),
            "currency_id": payload.get("currency_id"),
            "note": payload.get("note"),
        }

    def _statement_line_values(self, payload, statement):
        return [
            {
                "statement_id": statement.id,
                "sequence": index * 10,
                "description": line["description"],
                "product_id": line.get("product_id"),
                "quantity": line.get("quantity", 1.0),
                "price_unit": line.get("price_unit", 0.0),
                "amount": line["amount"],
                "tax_raw_text": line.get("tax_raw_text"),
                "tax_rate": line.get("tax_rate"),
                "tax_amount": line.get("tax_amount"),
                "reconciliation_clue": line.get("reconciliation_clue"),
                "charge_details": line.get("charge_details"),
                "tax_ids": [(6, 0, line.get("tax_ids", []))],
                "reconciliation_clues": line.get("reconciliation_clues", []),
            }
            for index, line in enumerate(payload.get("lines", []), 1)
        ]

    def _statement_payload_from_review(self, review_payload):
        if "header" not in review_payload:
            return review_payload
        header = review_payload.get("header") or {}
        return {
            "invoice_number": header.get("invoice_number"),
            "invoice_date": header.get("invoice_date"),
            "supplier_id": header.get("supplier_id"),
            "currency_id": header.get("currency_id"),
            "total_amount": header.get("total_amount", 0.0),
            "total_tax": header.get("total_tax", 0.0),
            "subtotal": header.get("subtotal", 0.0),
            "lines": [
                {
                    "product_id": line.get("product_id"),
                    "description": line.get("description"),
                    "quantity": line.get("quantity", 1.0),
                    "price_unit": line.get("unit_price", 0.0),
                    "amount": line.get("line_total_amount", line.get("subtotal", 0.0)),
                    "tax_ids": line.get("tax_ids", []),
                    "tax_raw_text": line.get("tax_raw_text"),
                    "reconciliation_clues": line.get("reconciliation_clues", []),
                }
                for line in review_payload.get("lines", [])
            ],
        }

    def _statement_payload_from_record(self):
        statement = self.statement_id
        return {
            "invoice_number": statement.invoice_number,
            "invoice_date": statement.invoice_date,
            "supplier_id": statement.supplier_id.id,
            "supplier_name": statement.supplier_name,
            "currency_id": statement.currency_id.id,
            "total_amount": statement.total_amount,
            "total_tax": statement.total_tax,
            "subtotal": statement.subtotal,
            "note": statement.note,
            "lines": [
                {
                    "description": line.description,
                    "product_id": line.product_id.id,
                    "quantity": line.quantity,
                    "price_unit": line.price_unit,
                    "amount": line.amount,
                    "tax_raw_text": line.tax_raw_text,
                    "tax_rate": line.tax_rate,
                    "tax_amount": line.tax_amount,
                    "reconciliation_clue": line.reconciliation_clue,
                    "charge_details": line.charge_details,
                    "tax_ids": line.tax_ids.ids,
                    "reconciliation_clues": line.reconciliation_clues or [],
                }
                for line in statement.line_ids
            ],
        }

    def _statement_payload_from_canonical(self, canonical):
        header = canonical.get("header") or {}
        value = lambda field: (header.get(field) or {}).get("value")
        supplier_name = value("supplier_raw_text")
        currency_name = value("currency_raw_text")
        supplier = self._find_supplier_partner(supplier_name)
        currency = self.env["res.currency"].search(
            ["|", ("name", "=", currency_name), ("symbol", "=", currency_name)],
            limit=1,
        ) if currency_name else self.env["res.currency"]
        return {
            "invoice_number": value("invoice_number"),
            "invoice_date": value("invoice_date"),
            "supplier_id": supplier.id or None,
            "supplier_name": supplier_name,
            "currency_id": currency.id or None,
            "total_amount": value("total_amount") or 0.0,
            "total_tax": value("total_tax") or 0.0,
            "subtotal": value("subtotal") or 0.0,
            "lines": [
                {
                    "description": (line.get("description") or {}).get("value"),
                    "amount": (line.get("amount") or {}).get("value"),
                    "price_unit": (line.get("amount") or {}).get("value"),
                    "tax_raw_text": (line.get("tax_raw_text") or {}).get("value"),
                    "tax_rate": (line.get("tax_rate") or {}).get("value"),
                    "tax_amount": (line.get("tax_amount") or {}).get("value"),
                    "reconciliation_clue": line.get("reconciliation_clue"),
                    "charge_details": line.get("charge_details"),
                    "reconciliation_clues": line.get("reconciliation_clues", []),
                }
                for line in canonical.get("lines", [])
            ],
        }

    def _log_statement_change(self, action, attempt, summary):
        self.env["vendor.invoice.import.log"].create({
            "task_id": self.id,
            "parse_attempt_id": attempt.id,
            "action": action,
            "snapshot_delta": summary,
        })

    def action_confirm_review_and_create_bill(self, review_payload):
        """Atomically save the review and create its draft vendor bill."""
        self.ensure_one()
        from ..services.bill_creator import confirm_review_and_create_bill

        return confirm_review_and_create_bill(self.env, self.id, review_payload)

    @api.model
    def cron_check_parsing_timeout(self):
        """Reconcile failed queue jobs and mark overdue parsing tasks."""
        from ..services.timeout_service import (
            check_parsing_timeout,
            reconcile_failed_queue_attempts,
        )

        reconcile_failed_queue_attempts(self.env)
        check_parsing_timeout(self.env)
