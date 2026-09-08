# © 2024 Wukong Digital. License LGPL-3.
import base64
import hashlib
import logging

from odoo import api, fields
from odoo.sql_db import db_connect
from odoo.tools import config


_logger = logging.getLogger(__name__)


def _mark_partial(attempt, operation, error):
    _logger.warning(
        "AI parse verification evidence is partial: operation=%s "
        "attempt_id=%s error_class=%s",
        operation,
        attempt.id,
        type(error).__name__,
    )
    try:
        with attempt.env.cr.savepoint():
            attempt.write({"observability_status": "partial"})
    except Exception as status_error:
        _logger.warning(
            "Could not persist partial verification status: attempt_id=%s "
            "error_class=%s",
            attempt.id,
            type(status_error).__name__,
        )


def _capture(attempt, operation, callback, default=None):
    try:
        with attempt.env.cr.savepoint():
            return callback()
    except Exception as error:
        _logger.exception(
            "AI parse observability persistence failed: task=%s attempt=%s "
            "artifact=%s exception=%s message=%s",
            attempt.task_id.id,
            attempt.id,
            operation,
            type(error).__name__,
            _safe_exception_message(error),
        )
        _mark_partial(attempt, operation, error)
        return default


def _capture_durable(attempt, operation, callback, default=None):
    """Commit diagnostic children independently from the queue transaction."""
    if config["test_enable"]:
        return _capture(
            attempt,
            operation,
            lambda: callback(attempt.env, attempt),
            default=default,
        )
    try:
        with db_connect(attempt.env.cr.dbname).cursor() as evidence_cr:
            evidence_env = api.Environment(
                evidence_cr,
                attempt.env.uid,
                dict(attempt.env.context),
            )
            durable_attempt = evidence_env[
                "vendor.invoice.import.parse.attempt"
            ].browse(attempt.id)
            result = callback(evidence_env, durable_attempt)
            evidence_cr.commit()
            return result
    except Exception as error:
        _logger.exception(
            "AI parse durable observability persistence failed: task=%s "
            "attempt=%s artifact=%s exception=%s message=%s",
            attempt.task_id.id,
            attempt.id,
            operation,
            type(error).__name__,
            _safe_exception_message(error),
        )
        _mark_partial(attempt, operation, error)
        return default


def _safe_exception_message(error):
    message = " ".join(str(error).split())
    return message[:500] if message else "No exception message."


def persist_page_artifacts(attempt, images):
    """Persist the exact ordered PNG bytes passed to the provider."""
    artifacts = []
    for page_no, image in enumerate(images, start=1):
        checksum = hashlib.sha256(image).hexdigest()

        def create_artifact(evidence_env, durable_attempt):
            evidence_env.cr.execute(
                "SELECT id FROM vendor_invoice_import_parse_attempt "
                "WHERE id=%s FOR UPDATE",
                (durable_attempt.id,),
            )
            artifact_model = evidence_env[
                "vendor.invoice.import.page.artifact"
            ].sudo()
            artifact = artifact_model.search([
                ("parse_attempt_id", "=", durable_attempt.id),
                ("page_no", "=", page_no),
            ], limit=1)
            if artifact:
                if (
                    artifact.checksum != checksum
                    or artifact.byte_size != len(image)
                ):
                    raise ValueError(
                        "Persisted page evidence differs from provider input."
                    )
                return artifact.id
            artifact = artifact_model.create({
                "parse_attempt_id": durable_attempt.id,
                "page_no": page_no,
                "mime_type": "image/png",
                "checksum": checksum,
                "byte_size": len(image),
                "rendered_at": fields.Datetime.now(),
            })
            attachment = evidence_env["ir.attachment"].sudo().create({
                "name": "attempt-%s-page-%s.png"
                % (durable_attempt.id, page_no),
                "type": "binary",
                "datas": base64.b64encode(image),
                "mimetype": "image/png",
                "res_model": artifact._name,
                "res_id": artifact.id,
                "res_field": "image_attachment_id",
                "public": False,
            })
            artifact.write({"image_attachment_id": attachment.id})
            return artifact.id

        artifacts.append(
            _capture_durable(
                attempt,
                "persist_page_%s" % page_no,
                create_artifact,
                default=False,
            )
        )
    return artifacts


def begin_provider_call(
    attempt,
    page_artifact,
    retry_index,
    provider_config,
    effective_prompt_snapshot,
    input_page_count=None,
    input_mode="rendered_images",
    input_document_type=None,
    rendered_image_count=0,
):
    artifacts = page_artifact if isinstance(page_artifact, (list, tuple)) else [page_artifact]
    artifact_ids = [
        artifact.id if hasattr(artifact, "id") else artifact
        for artifact in artifacts if artifact
    ]
    provider_snapshot = provider_config.name
    model_snapshot = provider_config.model_name

    def create_call(evidence_env, durable_attempt):
        evidence_env.cr.execute(
            "SELECT id FROM vendor_invoice_import_parse_attempt "
            "WHERE id=%s FOR UPDATE",
            (durable_attempt.id,),
        )
        call_model = evidence_env[
            "vendor.invoice.import.provider.call"
        ].sudo()
        last_call = call_model.search(
            [("parse_attempt_id", "=", durable_attempt.id)],
            order="call_sequence desc",
            limit=1,
        )
        return call_model.create({
            "parse_attempt_id": durable_attempt.id,
            "page_artifact_id": artifact_ids[0] if artifact_ids else False,
            "page_artifact_ids": [(6, 0, artifact_ids)],
            "input_page_count": (
                input_page_count if input_page_count is not None else len(artifact_ids)
            ),
            "input_mode": input_mode,
            "input_document_type": input_document_type,
            "rendered_image_count": rendered_image_count,
            "call_sequence": (last_call.call_sequence or 0) + 1,
            "retry_index": retry_index,
            "provider_snapshot": provider_snapshot,
            "model_snapshot": model_snapshot,
            "effective_prompt_snapshot": effective_prompt_snapshot,
            "request_started_at": fields.Datetime.now(),
            "outcome": "pending",
            "validation_status": "not_run",
        }).id

    return _capture_durable(
        attempt,
        "begin_provider_call",
        create_call,
        default=False,
    )


def finish_provider_call(
    attempt,
    provider_call,
    *,
    outcome,
    validation_status,
    http_status=None,
    raw_response=None,
    page_extraction_result=None,
    failure_stage=None,
    safe_error_summary=None,
    response_received=False,
    returned_page_count=None,
    failure_page_no=None,
):
    if not attempt:
        return
    provider_call_id = (
        provider_call.id
        if hasattr(provider_call, "id")
        else provider_call
    )
    if not provider_call_id:
        _mark_partial(
            attempt,
            "finish_provider_call_without_record",
            RuntimeError("ProviderCall evidence was not created."),
        )
        return

    values = {
        "outcome": outcome,
        "validation_status": validation_status,
        "http_status": http_status,
        "page_extraction_result": page_extraction_result,
        "failure_stage": failure_stage,
        "safe_error_summary": safe_error_summary,
        "returned_page_count": returned_page_count,
        "failure_page_no": failure_page_no,
    }
    if response_received:
        values["response_received_at"] = fields.Datetime.now()
    raw_bytes = None
    if raw_response is not None:
        raw_bytes = (
            raw_response.encode("utf-8")
            if isinstance(raw_response, str)
            else raw_response
        )

    def update_call(evidence_env, durable_attempt):
        durable_call = evidence_env[
            "vendor.invoice.import.provider.call"
        ].sudo().browse(provider_call_id).exists()
        if (
            not durable_call
            or durable_call.parse_attempt_id.id != durable_attempt.id
        ):
            raise ValueError("ProviderCall does not belong to ParseAttempt.")
        durable_call.write(values)
        if raw_bytes is None:
            return
        attachment = evidence_env["ir.attachment"].sudo().create({
            "name": "attempt-%s-call-%s-response.json"
            % (durable_attempt.id, durable_call.call_sequence),
            "type": "binary",
            "datas": base64.b64encode(raw_bytes),
            "mimetype": "application/json",
            "res_model": durable_call._name,
            "res_id": durable_call.id,
            "res_field": "raw_response_attachment_id",
            "public": False,
        })
        durable_call.write({
            "raw_response_attachment_id": attachment.id,
        })

    _capture_durable(
        attempt,
        "finish_provider_call",
        update_call,
    )


def persist_attempt_raw_response(attempt, raw_response):
    """Keep the existing Attempt-level combined response as compatibility data."""
    raw_bytes = (
        raw_response.encode("utf-8")
        if isinstance(raw_response, str)
        else raw_response
    )

    def attach_response():
        attachment = attempt.env["ir.attachment"].sudo().create({
            "name": "ai-response-%s.json" % attempt.sequence,
            "type": "binary",
            "datas": raw_bytes,
            "mimetype": "application/json",
            "res_model": attempt._name,
            "res_id": attempt.id,
            "res_field": "raw_response_attachment_id",
            "public": False,
        })
        attempt.sudo().write({"raw_response_attachment_id": attachment.id})
        return attachment

    return _capture(
        attempt,
        "persist_attempt_raw_response",
        attach_response,
        default=attempt.env["ir.attachment"],
    )


def record_provider_diagnostic(attempt, diagnostic):
    if not attempt:
        return

    def persist():
        diagnostics = list(attempt.provider_diagnostics or [])
        attempt.write({"provider_diagnostics": diagnostics + [diagnostic]})

    _capture(attempt, "record_provider_diagnostic", persist)


def record_internal_retry(attempt, retry_count):
    if attempt:
        _capture(
            attempt,
            "record_internal_retry",
            lambda: attempt.write({
                "attempt_internal_retry_count": retry_count,
            }),
        )


def set_attempt_failure_stage(attempt, failure_stage):
    if attempt and failure_stage:
        _capture(
            attempt,
            "set_attempt_failure_stage",
            lambda: attempt.sudo().write({"failure_stage": failure_stage}),
        )


def persist_canonical_snapshot(attempt, canonical_result):
    if attempt:
        _capture(
            attempt,
            "persist_canonical_snapshot",
            lambda: attempt.sudo().write({
                "canonical_result": canonical_result,
            }),
        )


def finalize_observability(attempt):
    if not attempt:
        return
    attempt.invalidate_recordset(["observability_status"])
    if attempt.observability_status == "partial":
        return
    _capture(
        attempt,
        "finalize_observability",
        lambda: attempt.write({"observability_status": "complete"}),
    )
