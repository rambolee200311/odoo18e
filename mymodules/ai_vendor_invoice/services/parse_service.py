# © 2024 Wukong Digital. License LGPL-3.
import logging
import traceback

from odoo import api, fields
from odoo.sql_db import db_connect
from psycopg2 import OperationalError

from ..adapters import (
    AIProviderPermanentError,
    AIProviderTemporaryError,
    adapter_for,
)
from ..adapters.aibase import (
    EXTRACTION_CONTRACT_VERSION,
    PROMPT_VERSION,
)
from ..adapters.document_normalizer import DocumentNormalizationError
from . import observability_service
from .mapping_service import do_mapping
from .pdf_preprocessor import PDFPreprocessorError, prepare_provider_input


_logger = logging.getLogger(__name__)


def _safe_error_summary(error):
    """Return a stable user message without provider or transport details."""
    if isinstance(error, PDFPreprocessorError):
        return "The source PDF could not be prepared for AI parsing."
    if isinstance(error, AIProviderTemporaryError):
        return "The AI provider is temporarily unavailable. Please try again."
    if isinstance(error, AIProviderPermanentError):
        return "The AI provider rejected the parse request."
    return "AI parsing failed. Please try again or contact an administrator."


def _safe_exception_message(error):
    message = " ".join(str(error).split())
    return message[:500] if message else "No exception message."


def _traceback_location(error):
    frames = traceback.extract_tb(error.__traceback__)
    if not frames:
        return None
    frame = frames[-1]
    return "%s:%s:%s" % (
        frame.filename,
        frame.lineno,
        frame.name,
    )


def _failure_stage(env, attempt_id, error, default="OTHER"):
    if getattr(error, "failure_stage", None):
        return error.failure_stage
    if isinstance(error, PDFPreprocessorError):
        return "PDF_PREPROCESS"
    if isinstance(error, DocumentNormalizationError):
        return "DOCUMENT_NORMALIZATION"
    last_call = env["vendor.invoice.import.provider.call"].search(
        [
            ("parse_attempt_id", "=", attempt_id),
            ("failure_stage", "!=", False),
        ],
        order="call_sequence desc",
        limit=1,
    )
    return last_call.failure_stage or default


def _failed_attempt(env, task_id, attempt_id, error, failure_stage=None):
    summary = _safe_error_summary(error)
    stage = failure_stage or _failure_stage(env, attempt_id, error)
    attempt = env["vendor.invoice.import.parse.attempt"].browse(attempt_id)
    observability_service.record_provider_diagnostic(attempt, {
        "diagnostic_type": "failure",
        "failure_stage": stage,
        "exception_class": type(error).__name__,
        "safe_exception_message": _safe_exception_message(error),
        "traceback_location": _traceback_location(error),
        "provider_call_id": (
            attempt.provider_call_ids[-1].id
            if attempt.provider_call_ids else None
        ),
        "raw_response_attachment_id": (
            attempt.provider_call_ids[-1].raw_response_attachment_id.id
            if attempt.provider_call_ids
            and attempt.provider_call_ids[-1].raw_response_attachment_id
            else None
        ),
    })
    try:
        _write_failed_attempt(env, task_id, attempt_id, summary, stage)
    except OperationalError:
        # A serialization failure aborts the queue transaction. Roll it back
        # before retrying the terminal projection in a fresh transaction.
        env.cr.rollback()
        with db_connect(env.cr.dbname).cursor() as lifecycle_cr:
            lifecycle_env = api.Environment(lifecycle_cr, env.uid, dict(env.context))
            _write_failed_attempt(
                lifecycle_env,
                task_id,
                attempt_id,
                summary,
                stage,
            )
            lifecycle_env[
                "vendor.invoice.import.parse.attempt"
            ].browse(attempt_id).write({"observability_status": "partial"})
            lifecycle_cr.commit()
        env.invalidate_all()
    else:
        observability_service.finalize_observability(
            env["vendor.invoice.import.parse.attempt"].browse(attempt_id)
        )


def _write_failed_attempt(env, task_id, attempt_id, summary, failure_stage):
    task = env["wd.lock.service"].lock_task(task_id)
    attempt = env["wd.lock.service"].lock_attempt(attempt_id)
    if attempt.status == "cancelled":
        return
    now = fields.Datetime.now()
    attempt.write({
        "status": "failed",
        "finished_at": now,
        "completed_at": now,
        "error_message": summary,
        "error_summary": summary,
    })
    observability_service.set_attempt_failure_stage(
        attempt,
        failure_stage,
    )
    if task.current_parse_attempt_id == attempt and task.state == "parsing":
        task.write({"state": "error"})
        _audit(env, task, attempt, "ai_parse", "AI parse failed.")


def _audit(env, task, attempt, action, snapshot_delta):
    env["vendor.invoice.import.log"].create({
        "task_id": task.id,
        "parse_attempt_id": attempt.id if attempt else False,
        "action": action,
        "snapshot_delta": snapshot_delta,
    })


def _publish_attempt_running(env, attempt):
    """Publish worker-start observability without holding the parse transaction."""
    if env.context.get("ai_invoice_sync"):
        now = fields.Datetime.now()
        attempt.write({
            "status": "running",
            "started_at": now,
            "last_activity_at": now,
        })
        return
    with db_connect(env.cr.dbname).cursor() as lifecycle_cr:
        lifecycle_env = api.Environment(lifecycle_cr, env.uid, dict(env.context))
        lifecycle_attempt = lifecycle_env[
            "vendor.invoice.import.parse.attempt"
        ].browse(attempt.id)
        now = fields.Datetime.now()
        lifecycle_attempt.write({
            "status": "running",
            "started_at": now,
            "last_activity_at": now,
        })
        lifecycle_cr.commit()
    attempt.invalidate_recordset(["status", "started_at", "last_activity_at"])


def start_parse(env, task_id, provider_config_id, synchronous=False):
    task = env["wd.lock.service"].lock_task(task_id)
    task.ensure_one()
    if task.state not in ("to_parse", "awaiting_review", "error"):
        raise ValueError("Task cannot start an AI parse in its current state.")
    active_attempt = env["vendor.invoice.import.parse.attempt"].search(
        [
            ("task_id", "=", task.id),
            ("status", "in", ("queued", "running")),
        ],
        limit=1,
    )
    if active_attempt:
        raise ValueError("This task already has an AI parse attempt in progress.")
    provider_config = env["wd.ai.provider.config"].browse(provider_config_id)
    submitted_at = fields.Datetime.now()
    attempt = env["vendor.invoice.import.parse.attempt"].create({
        "task_id": task.id,
        "sequence": task._get_next_attempt_sequence(),
        "provider_config_id": provider_config_id,
        "status": "queued",
        "prompt_version": PROMPT_VERSION,
        "extraction_contract_version": EXTRACTION_CONTRACT_VERSION,
        "model_name_snapshot": provider_config.model_name,
        "submitted_at": submitted_at,
    })
    task.write({
        "current_parse_attempt_id": attempt.id,
        "state": "parsing",
        "enter_parsing_datetime": fields.Datetime.now(),
        "human_reviewed": False,
    })
    _audit(env, task, attempt, "ai_re_run" if attempt.sequence > 1 else "ai_parse",
           "Queued parse attempt %s" % attempt.sequence)
    if synchronous:
        return run_parse_attempt(
            task.with_context(ai_invoice_sync=True).env,
            task.id,
            attempt.id,
        ) or attempt
    attempt.action_enqueue_parse()
    return attempt


def run_parse_attempt(env, task_id, attempt_id):
    task = env["vendor.invoice.import.task"].browse(task_id)
    task = task.with_company(task.company_id)
    attempt = env["vendor.invoice.import.parse.attempt"].browse(attempt_id)
    attempt.ensure_one()
    if attempt.status in ("success", "failed", "superseded", "cancelled"):
        return False
    if not (task.state == "parsing" and task.current_parse_attempt_id == attempt
            and attempt.status in ("queued", "running")):
        now = fields.Datetime.now()
        attempt.write({
            "status": "superseded",
            "finished_at": now,
            "completed_at": now,
            "error_message": "This parse attempt was superseded by a newer attempt.",
            "error_summary": "This parse attempt was superseded by a newer attempt.",
        })
        return False
    _publish_attempt_running(env, attempt)
    try:
        adapter = adapter_for(env, attempt.provider_config_id)
        input_mode = attempt.provider_config_id.document_input_mode or "rendered_images"
        adapter.validate_input_mode(input_mode)
        provider_input = prepare_provider_input(
            task.source_pdf_attachment_id,
            mode=input_mode,
        )
        if input_mode == "rendered_images" and provider_input.get("images"):
            page_artifacts = observability_service.persist_page_artifacts(
                attempt,
                provider_input["images"],
            )
            if hasattr(provider_input, "page_artifacts"):
                provider_input.page_artifacts = tuple(page_artifacts)
            else:
                provider_input["page_artifacts"] = page_artifacts
        canonical, raw = adapter.parse_pdf(
            provider_input, attempt.provider_config_id,
            attempt.provider_config_id.max_internal_retry, attempt,
        )
    except PDFPreprocessorError as error:
        _failed_attempt(env, task.id, attempt.id, error)
        return False
    except (AIProviderTemporaryError, AIProviderPermanentError) as error:
        _failed_attempt(env, task.id, attempt.id, error)
        return False
    except Exception as error:
        _failed_attempt(env, task.id, attempt.id, error)
        return False
    observability_service.persist_attempt_raw_response(attempt, raw)
    observability_service.persist_canonical_snapshot(attempt, canonical)
    try:
        mapping = do_mapping(env, canonical)
    except Exception as error:
        _logger.exception(
            "AI parse failed: task=%s attempt=%s failure_stage=MAPPING "
            "exception=%s message=%s",
            task.id,
            attempt.id,
            type(error).__name__,
            _safe_exception_message(error),
        )
        _failed_attempt(
            env,
            task.id,
            attempt.id,
            error,
            failure_stage="MAPPING",
        )
        return False
    # Re-check after HTTP/mapping: the worker may have been superseded.
    task.invalidate_recordset(["state", "current_parse_attempt_id"])
    attempt.invalidate_recordset(["status"])
    if not (task.state == "parsing" and task.current_parse_attempt_id == attempt
            and attempt.status == "running"):
        if attempt.status in ("success", "failed", "superseded", "cancelled"):
            return False
        now = fields.Datetime.now()
        attempt.write({
            "status": "superseded",
            "canonical_result": canonical,
            "mapping_result": mapping,
            "finished_at": now,
            "completed_at": now,
        })
        return False
    task = env["wd.lock.service"].lock_task(task.id)
    task = task.with_company(task.company_id)
    attempt = env["wd.lock.service"].lock_attempt(attempt.id)
    task.invalidate_recordset(["state", "current_parse_attempt_id"])
    attempt.invalidate_recordset(["status"])
    if not (task.state == "parsing" and task.current_parse_attempt_id == attempt
            and attempt.status == "running"):
        if attempt.status in ("success", "failed", "superseded", "cancelled"):
            return False
        now = fields.Datetime.now()
        attempt.write({
            "status": "superseded",
            "finished_at": now,
            "completed_at": now,
        })
        return False
    completed_at = fields.Datetime.now()
    attempt.write({
        "status": "success",
        "canonical_result": canonical,
        "mapping_result": mapping,
        "finished_at": completed_at,
        "completed_at": completed_at,
        "last_activity_at": completed_at,
    })
    if input_mode == "native_pdf":
        task._create_prefilled_statement_from_canonical(attempt, canonical)
    task.write({"state": "error" if canonical.get("is_multi_invoice")
                else "awaiting_review"})
    _audit(env, task, attempt, "ai_parse", "AI parse completed successfully.")
    observability_service.finalize_observability(attempt)
    return True
