# © 2024 Wukong Digital. License LGPL-3.
import base64
import json
from unittest.mock import Mock, patch

import httpx
from jsonschema import ValidationError
from openai import APIConnectionError, APIStatusError

from odoo import api, fields
from odoo.exceptions import AccessError
from odoo.modules.registry import Registry
from odoo.tests.common import TransactionCase

from ..adapters.deepseek import DeepSeekAIProviderAdapter
from ..adapters.base import AIProviderTemporaryError
from ..adapters.openai import OpenAIAIProviderAdapter
from ..services import observability_service, parse_service
from ..schemas.document_extraction import INVOICE_EXTRACTION_RESULT_SCHEMA


def _strict_response_text():
    return {
        "invoice_number": None,
        "invoice_date": None,
        "due_date": None,
        "currency": None,
        "supplier": {"name": None, "address": None, "vat_number": None},
        "buyer": {"name": None, "address": None},
        "lines": [],
        "subtotal": None,
        "total_tax": None,
        "total_amount": None,
    }


class ObservabilityCase(TransactionCase):
    def setUp(self):
        super().setUp()
        source = self.env["ir.attachment"].create({
            "name": "observability.pdf",
            "type": "binary",
            "datas": base64.b64encode(b"%PDF-1.4"),
            "res_model": "vendor.invoice.import.task",
            "public": False,
        })
        self.provider = self.env["wd.ai.provider.config"].create({
            "name": "Observability DeepSeek",
            "api_base_url": "https://example.invalid",
            "model_name": "deepseek-observability",
            "max_internal_retry": 1,
        })
        self.task = self.env["vendor.invoice.import.task"].create({
            "source_pdf_attachment_id": source.id,
            "selected_provider_config_id": self.provider.id,
            "state": "parsing",
        })
        self.attempt = self.env[
            "vendor.invoice.import.parse.attempt"
        ].create({
            "task_id": self.task.id,
            "sequence": 1,
            "provider_config_id": self.provider.id,
            "status": "queued",
        })
        self.task.current_parse_attempt_id = self.attempt

    def _user(self, name, group):
        internal_group = self.env.ref("base.group_user")
        return self.env["res.users"].with_context(
            no_reset_password=True,
        ).create({
            "name": name,
            "login": "%s@example.invalid" % name.lower().replace(" ", "."),
            "company_id": self.env.company.id,
            "company_ids": [(6, 0, [self.env.company.id])],
            "groups_id": [(6, 0, [internal_group.id, group.id])],
        })


class TestPageArtifactEvidence(ObservabilityCase):
    def test_page_order_and_actual_bytes_are_persisted(self):
        images = [b"first-png", b"second-png"]

        artifact_ids = observability_service.persist_page_artifacts(
            self.attempt,
            images,
        )
        artifacts = self.env[
            "vendor.invoice.import.page.artifact"
        ].browse(artifact_ids)

        self.assertEqual([artifact.page_no for artifact in artifacts], [1, 2])
        self.assertEqual(
            [artifact.image_attachment_id.raw for artifact in artifacts],
            images,
        )
        self.assertEqual(
            [artifact.byte_size for artifact in artifacts],
            [len(image) for image in images],
        )
        self.assertEqual(
            artifacts[0].image_attachment_id.res_field,
            "image_attachment_id",
        )
        self.assertNotEqual(artifacts[0].checksum, artifacts[1].checksum)

    def test_page_attachment_failure_marks_partial_without_raising(self):
        attachment_model = type(self.env["ir.attachment"])
        with patch.object(
            attachment_model,
            "create",
            side_effect=RuntimeError("diagnostic storage unavailable"),
        ):
            artifacts = observability_service.persist_page_artifacts(
                self.attempt,
                [b"png"],
            )

        self.assertFalse(artifacts[0])
        self.assertEqual(self.attempt.observability_status, "partial")

    def test_derived_verification_statuses_reflect_persisted_facts(self):
        self.assertEqual(
            self.attempt.evidence_pdf_status,
            "not_available_for_historical_attempt",
        )
        self.assertEqual(
            self.attempt.evidence_page_extraction_status,
            "not_available_for_historical_attempt",
        )
        artifact_id = observability_service.persist_page_artifacts(
            self.attempt,
            [b"png"],
        )[0]
        artifact = self.env[
            "vendor.invoice.import.page.artifact"
        ].browse(artifact_id)
        self.assertEqual(artifact.preview_status, "generated")
        call = self.env["vendor.invoice.import.provider.call"].create({
            "parse_attempt_id": self.attempt.id,
            "page_artifact_id": artifact.id,
            "call_sequence": 1,
            "retry_index": 0,
            "provider_snapshot": "deepseek",
            "model_snapshot": "vision",
            "outcome": "response_invalid",
            "validation_status": "fail",
            "failure_stage": "PAGE_SCHEMA_VALIDATION",
        })
        self.assertEqual(call.page_extraction_status, "failed_before_stage")
        self.assertEqual(
            self.attempt.evidence_page_extraction_status,
            "failed_before_stage",
        )
        self.assertEqual(self.attempt.failure_page_no, 1)
        self.assertEqual(self.attempt.failure_call_sequence, 1)
        self.assertEqual(self.attempt.evidence_canonical_status, "failed_before_stage")
        self.assertEqual(self.attempt.evidence_mapping_status, "failed_before_stage")


class TestProviderCallEvidence(ObservabilityCase):
    def test_native_pdf_invalid_structured_output_has_schema_stage(self):
        adapter = OpenAIAIProviderAdapter.__new__(OpenAIAIProviderAdapter)
        response = Mock()
        response.model_dump_json.return_value = '{"output": []}'
        response.output_text = '{"invoice_number": "incomplete"}'
        client = Mock()
        client.files.create.return_value.id = "file-native"
        client.responses.create.return_value = response
        adapter._build_client = Mock(return_value=client)

        with self.assertRaises(AIProviderPermanentError):
            adapter.parse_native_pdf(
                {
                    "mode": "native_pdf",
                    "document_bytes": b"%PDF",
                    "source": {"page_count": 1},
                },
                self.provider,
                "Extract as JSON.",
                self.attempt,
            )

        self.assertEqual(
            self.attempt.provider_call_ids.failure_stage,
            "PAGE_SCHEMA_VALIDATION",
        )

    def test_native_pdf_success_creates_one_provider_call(self):
        adapter = OpenAIAIProviderAdapter.__new__(OpenAIAIProviderAdapter)
        response = Mock()
        response.model_dump_json.return_value = '{"output": []}'
        response.output_text = json.dumps(_strict_response_text())
        client = Mock()
        client.files.create.return_value.id = "file-native"
        client.responses.create.return_value = response
        adapter._build_client = Mock(return_value=client)

        result, _raw, _content = adapter.parse_native_pdf(
            {
                "mode": "native_pdf",
                "document_bytes": b"%PDF",
                "source": {"page_count": 3},
            },
            self.provider,
            "Extract as JSON.",
            self.attempt,
        )

        self.assertEqual(result["lines"], [])
        calls = self.attempt.provider_call_ids
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls.input_mode, "native_pdf")
        self.assertEqual(calls.input_document_type, "application/pdf")
        self.assertEqual(calls.input_page_count, 3)
        self.assertEqual(calls.rendered_image_count, 0)
        self.assertEqual(calls.outcome, "success")
        request = client.responses.create.call_args.kwargs
        self.assertEqual(request["text"]["format"]["type"], "json_schema")
        self.assertTrue(request["text"]["format"]["strict"])
        self.assertEqual(
            request["text"]["format"]["schema"],
            INVOICE_EXTRACTION_RESULT_SCHEMA,
        )
        self.assertEqual(request["reasoning"], {"effort": "low"})

    def test_native_pdf_failure_keeps_provider_call_evidence(self):
        adapter = OpenAIAIProviderAdapter.__new__(OpenAIAIProviderAdapter)
        client = Mock()
        client.files.create.side_effect = RuntimeError("native transport failed")
        adapter._build_client = Mock(return_value=client)

        with self.assertRaisesRegex(RuntimeError, "native transport failed"):
            adapter.parse_native_pdf(
                {
                    "mode": "native_pdf",
                    "document_bytes": b"%PDF",
                    "source": {"page_count": 1},
                },
                self.provider,
                "Extract as JSON.",
                self.attempt,
            )

        call = self.attempt.provider_call_ids
        self.assertEqual(len(call), 1)
        self.assertEqual(call.outcome, "failed")
        self.assertEqual(call.failure_stage, "PAGE_PROVIDER_REQUEST")
        self.assertEqual(
            call.safe_error_summary,
            "OpenAI native PDF request failed.",
        )

    def test_native_pdf_timeout_retries_with_auditable_calls(self):
        adapter = OpenAIAIProviderAdapter.__new__(OpenAIAIProviderAdapter)
        response = Mock()
        response.model_dump_json.return_value = '{"output": []}'
        response.output_text = json.dumps(_strict_response_text())
        client = Mock()
        client.files.create.return_value.id = "file-native"
        client.responses.create.side_effect = [
            APIConnectionError(
                request=httpx.Request("POST", "https://example.invalid")
            ),
            response,
        ]
        adapter._build_client = Mock(return_value=client)
        self.provider.max_internal_retry = 1

        with patch.object(adapter, "_wait_before_retry") as wait:
            adapter.parse_native_pdf(
                {
                    "mode": "native_pdf",
                    "document_bytes": b"%PDF",
                    "source": {"page_count": 1},
                },
                self.provider,
                "Extract as JSON.",
                self.attempt,
            )

        self.assertEqual(client.files.create.call_count, 2)
        self.assertEqual(client.responses.create.call_count, 2)
        self.assertEqual(
            self.attempt.provider_call_ids.mapped("retry_index"),
            [0, 1],
        )
        self.assertEqual(self.attempt.attempt_internal_retry_count, 1)
        wait.assert_called_once_with(0)

    def test_native_pdf_retry_exhaustion_makes_no_fourth_call(self):
        adapter = OpenAIAIProviderAdapter.__new__(OpenAIAIProviderAdapter)
        client = Mock()
        client.files.create.side_effect = [
            APIConnectionError(
                request=httpx.Request("POST", "https://example.invalid")
            ),
            APIConnectionError(
                request=httpx.Request("POST", "https://example.invalid")
            ),
            APIConnectionError(
                request=httpx.Request("POST", "https://example.invalid")
            ),
        ]
        adapter._build_client = Mock(return_value=client)
        self.provider.max_internal_retry = 2

        with patch.object(adapter, "_wait_before_retry"):
            with self.assertRaisesRegex(
                AIProviderTemporaryError,
                "AI provider request temporarily unavailable.",
            ):
                adapter.parse_native_pdf(
                    {
                        "mode": "native_pdf",
                        "document_bytes": b"%PDF",
                        "source": {"page_count": 1},
                    },
                    self.provider,
                    "Extract as JSON.",
                    self.attempt,
                )

        self.assertEqual(client.files.create.call_count, 3)
        self.assertEqual(
            self.attempt.provider_call_ids.mapped("retry_index"),
            [0, 1, 2],
        )


class TestFailureDiagnostics(ObservabilityCase):
    def test_persistence_failure_is_logged(self):
        with patch.object(
            observability_service._logger,
            "exception",
        ) as log_exception:
            observability_service._capture(
                self.attempt,
                "canonical",
                lambda: (_ for _ in ()).throw(
                    RuntimeError("diagnostic storage unavailable")
                ),
            )

        log_exception.assert_called_once()
        self.assertEqual(log_exception.call_args.args[3], "canonical")

    def test_mapping_failure_preserves_safe_diagnostic(self):
        parse_service._failed_attempt(
            self.env,
            self.task.id,
            self.attempt.id,
            ValueError("diagnostic mapping failure"),
            failure_stage="MAPPING",
        )

        self.assertEqual(self.attempt.status, "failed")
        self.assertEqual(self.attempt.failure_stage, "MAPPING")
        diagnostic = self.attempt.provider_diagnostics[-1]
        self.assertEqual(diagnostic["exception_class"], "ValueError")
        self.assertEqual(
            diagnostic["safe_exception_message"],
            "diagnostic mapping failure",
        )


class TestProviderCallEvidenceRegression(ObservabilityCase):
    def test_each_real_retry_has_immutable_call_evidence(self):
        artifact_id = observability_service.persist_page_artifacts(
            self.attempt,
            [b"png"],
        )[0]
        artifact = self.env[
            "vendor.invoice.import.page.artifact"
        ].browse(artifact_id)
        adapter = DeepSeekAIProviderAdapter.__new__(
            DeepSeekAIProviderAdapter
        )
        response = Mock()
        response.model_dump.return_value = {
            "choices": [{
                "message": {
                    "content": '{"pages": [{"page_number": 1, "header": {}, "lines": []}]}',
                },
            }],
        }
        response.model_dump_json.return_value = '{"provider": "response"}'
        client = Mock()
        client.chat.completions.create.side_effect = [
            APIConnectionError(
                request=httpx.Request("POST", "https://example.invalid")
            ),
            response,
        ]

        result, _raw = adapter._parse_page_batch(
            client,
            self.provider,
            [b"png"],
            1,
            self.attempt,
            0,
            1,
            artifact,
        )

        calls = self.attempt.provider_call_ids.sorted("call_sequence")
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls.mapped("retry_index"), [0, 1])
        self.assertEqual(calls.mapped("outcome"), ["no_response", "success"])
        self.assertEqual(calls[1].page_extraction_result, result)
        self.assertEqual(calls[1].validation_status, "pass")
        self.assertEqual(calls[1].raw_response_attachment_id.raw,
                         b'{"provider": "response"}')
        self.assertEqual(
            calls[1].raw_response_attachment_id.res_field,
            "raw_response_attachment_id",
        )
        snapshot = calls[1].effective_prompt_snapshot
        self.provider.model_name = "changed-after-call"
        self.assertEqual(
            calls[1].model_snapshot,
            "deepseek-observability",
        )
        self.assertEqual(calls[1].effective_prompt_snapshot, snapshot)
        self.assertNotIn("image_url", snapshot)
        self.assertNotIn("api_key", snapshot)

    def test_schema_failure_keeps_raw_response_and_failure_stage(self):
        artifact_id = observability_service.persist_page_artifacts(
            self.attempt,
            [b"png"],
        )[0]
        artifact = self.env[
            "vendor.invoice.import.page.artifact"
        ].browse(artifact_id)
        adapter = DeepSeekAIProviderAdapter.__new__(
            DeepSeekAIProviderAdapter
        )
        response = Mock()
        response.model_dump.return_value = {
            "choices": [{
                "message": {
                    "content": '{"unexpected": true}',
                },
            }],
        }
        response.model_dump_json.return_value = '{"raw": "invalid-schema"}'
        client = Mock()
        client.chat.completions.create.return_value = response

        try:
            adapter._parse_page_batch(
                client,
                self.provider,
                [b"png"],
                0,
                self.attempt,
                0,
                1,
                artifact,
            )
        except ValidationError as error:
            self.assertEqual(
                error.failure_stage,
                "PAGE_SCHEMA_VALIDATION",
            )
        else:
            self.fail("Expected page schema validation to fail.")

        provider_call = self.attempt.provider_call_ids
        self.assertEqual(provider_call.outcome, "response_invalid")
        self.assertEqual(provider_call.validation_status, "fail")
        self.assertEqual(
            provider_call.failure_stage,
            "PAGE_SCHEMA_VALIDATION",
        )
        self.assertEqual(
            provider_call.raw_response_attachment_id.raw,
            b'{"raw": "invalid-schema"}',
        )
        self.assertFalse(provider_call.page_extraction_result)

    def test_rerun_evidence_is_owned_by_its_attempt(self):
        first_id = observability_service.persist_page_artifacts(
            self.attempt,
            [b"first"],
        )[0]
        second_attempt = self.env[
            "vendor.invoice.import.parse.attempt"
        ].create({
            "task_id": self.task.id,
            "sequence": 2,
            "provider_config_id": self.provider.id,
            "status": "queued",
        })
        second_id = observability_service.persist_page_artifacts(
            second_attempt,
            [b"second"],
        )[0]
        first = self.env[
            "vendor.invoice.import.page.artifact"
        ].browse(first_id)
        second = self.env[
            "vendor.invoice.import.page.artifact"
        ].browse(second_id)

        self.assertEqual(first.parse_attempt_id, self.attempt)
        self.assertEqual(second.parse_attempt_id, second_attempt)
        self.assertNotEqual(first.image_attachment_id.raw,
                            second.image_attachment_id.raw)


class TestObservabilityFailureIsolation(ObservabilityCase):
    def test_partial_evidence_does_not_change_success_result(self):
        adapter = Mock()
        adapter.parse_pdf.return_value = (
            {"header": {}, "lines": [], "is_multi_invoice": False},
            base64.b64encode(b"[]"),
        )

        def publish_running(_env, attempt):
            attempt.write({
                "status": "running",
                "started_at": fields.Datetime.now(),
            })

        def partial_pages(attempt, _images):
            attempt.write({"observability_status": "partial"})
            return []

        with patch.object(
            parse_service,
            "_publish_attempt_running",
            side_effect=publish_running,
        ), patch.object(
            parse_service,
            "prepare_provider_input",
            return_value={"type": "pages", "images": [b"png"]},
        ), patch.object(
            parse_service,
            "adapter_for",
            return_value=adapter,
        ), patch.object(
            parse_service,
            "do_mapping",
            return_value={},
        ), patch.object(
            observability_service,
            "persist_page_artifacts",
            side_effect=partial_pages,
        ):
            result = parse_service.run_parse_attempt(
                self.env,
                self.task.id,
                self.attempt.id,
            )

        self.assertTrue(result)
        self.assertEqual(self.attempt.status, "success")
        self.assertEqual(self.task.state, "awaiting_review")
        self.assertEqual(self.attempt.observability_status, "partial")

    def test_duplicate_worker_does_not_clobber_terminal_attempt(self):
        def publish_running(_env, attempt):
            attempt.write({
                "status": "running",
                "started_at": fields.Datetime.now(),
            })

        adapter = Mock()

        def winner_completed(*_args, **_kwargs):
            self.attempt.write({"status": "success"})
            self.task.write({"state": "awaiting_review"})
            return (
                {"header": {}, "lines": [], "is_multi_invoice": False},
                base64.b64encode(b"[]"),
            )

        adapter.parse_pdf.side_effect = winner_completed
        with patch.object(
            parse_service,
            "_publish_attempt_running",
            side_effect=publish_running,
        ), patch.object(
            parse_service,
            "prepare_provider_input",
            return_value={"type": "pages", "images": [b"png"]},
        ), patch.object(
            parse_service,
            "adapter_for",
            return_value=adapter,
        ), patch.object(
            parse_service,
            "do_mapping",
            return_value={},
        ):
            result = parse_service.run_parse_attempt(
                self.env,
                self.task.id,
                self.attempt.id,
            )

        self.assertFalse(result)
        self.assertEqual(self.attempt.status, "success")
        self.assertEqual(self.task.state, "awaiting_review")


class TestObservabilitySecurity(ObservabilityCase):
    def test_queue_user_can_capture_system_authored_evidence(self):
        user = self._user(
            "Evidence Queue User",
            self.env.ref("ai_vendor_invoice.group_ai_invoice_user"),
        )
        attempt = self.attempt.with_user(user)

        artifact_id = observability_service.persist_page_artifacts(
            attempt,
            [b"queue-user-png"],
        )[0]
        artifact = self.env[
            "vendor.invoice.import.page.artifact"
        ].browse(artifact_id)
        provider_call_id = observability_service.begin_provider_call(
            attempt,
            artifact_id,
            0,
            self.provider.with_user(user),
            {"system": "safe", "user": "safe", "checksum": "sum"},
        )
        observability_service.finish_provider_call(
            attempt,
            provider_call_id,
            outcome="success",
            validation_status="pass",
            http_status=200,
            raw_response=b'{"response": true}',
            page_extraction_result={"page_number": 1},
            response_received=True,
        )
        provider_call = self.env[
            "vendor.invoice.import.provider.call"
        ].browse(provider_call_id)
        observability_service.set_attempt_failure_stage(
            attempt,
            "PAGE_SCHEMA_VALIDATION",
        )

        self.assertTrue(artifact)
        self.assertTrue(provider_call)
        self.assertEqual(provider_call.outcome, "success")
        self.assertEqual(
            self.attempt.failure_stage,
            "PAGE_SCHEMA_VALIDATION",
        )

    def test_sensitive_evidence_is_restricted_by_role(self):
        artifact_id = observability_service.persist_page_artifacts(
            self.attempt,
            [b"png"],
        )[0]
        artifact = self.env[
            "vendor.invoice.import.page.artifact"
        ].browse(artifact_id)
        provider_call_id = observability_service.begin_provider_call(
            self.attempt,
            artifact_id,
            0,
            self.provider,
            {"system": "safe", "user": "safe", "checksum": "sum"},
        )
        observability_service.finish_provider_call(
            self.attempt,
            provider_call_id,
            outcome="success",
            validation_status="pass",
            http_status=200,
            raw_response=b'{"response": true}',
            page_extraction_result={"page_number": 1},
            response_received=True,
        )
        provider_call = self.env[
            "vendor.invoice.import.provider.call"
        ].browse(provider_call_id)
        user = self._user(
            "Evidence User",
            self.env.ref("ai_vendor_invoice.group_ai_invoice_user"),
        )
        reviewer = self._user(
            "Evidence Reviewer",
            self.env.ref("ai_vendor_invoice.group_reviewer"),
        )
        manager = self._user(
            "Evidence Manager",
            self.env.ref("ai_vendor_invoice.group_config_manager"),
        )

        with self.assertRaises(AccessError):
            artifact.with_user(user).check_access("read")
        artifact.with_user(reviewer).check_access("read")
        provider_call.with_user(reviewer).check_access("read")
        with self.assertRaises(AccessError):
            provider_call.raw_response_attachment_id.with_user(
                reviewer
            ).check("read")
        provider_call.raw_response_attachment_id.with_user(manager).check(
            "read"
        )
        artifact.image_attachment_id.with_user(reviewer).check("read")

        reviewer_fields = provider_call.with_user(reviewer).fields_get()
        manager_fields = provider_call.with_user(manager).fields_get()
        self.assertNotIn("effective_prompt_snapshot", reviewer_fields)
        self.assertNotIn("raw_response_attachment_id", reviewer_fields)
        self.assertIn("effective_prompt_snapshot", manager_fields)
        self.assertIn("raw_response_attachment_id", manager_fields)

    def test_cross_company_evidence_is_denied(self):
        other_company = self.env["res.company"].search(
            [("id", "!=", self.env.company.id)],
            limit=1,
        )
        if not other_company:
            other_company = self.env["res.company"].create({
                "name": "Other Evidence Company",
            })
        source = self.env["ir.attachment"].create({
            "name": "other-company.pdf",
            "type": "binary",
            "datas": base64.b64encode(b"%PDF-1.4"),
            "res_model": "vendor.invoice.import.task",
            "public": False,
        })
        task = self.env["vendor.invoice.import.task"].create({
            "company_id": other_company.id,
            "source_pdf_attachment_id": source.id,
            "selected_provider_config_id": self.provider.id,
            "state": "parsing",
        })
        attempt = self.env["vendor.invoice.import.parse.attempt"].create({
            "task_id": task.id,
            "sequence": 1,
            "provider_config_id": self.provider.id,
            "status": "queued",
        })
        artifact_id = observability_service.persist_page_artifacts(
            attempt,
            [b"other-company-png"],
        )[0]
        artifact = self.env[
            "vendor.invoice.import.page.artifact"
        ].browse(artifact_id)
        manager = self._user(
            "Scoped Evidence Manager",
            self.env.ref("ai_vendor_invoice.group_config_manager"),
        )

        with self.assertRaises(AccessError):
            artifact.with_user(manager).check_access("read")


class TestDurableEvidenceTransaction(TransactionCase):
    def test_evidence_survives_caller_transaction_rollback(self):
        dbname = self.env.cr.dbname
        with Registry(dbname).cursor() as setup_cr:
            setup_env = api.Environment(setup_cr, self.env.uid, {})
            old_sources = setup_env["ir.attachment"].search([
                ("name", "=", "durable-evidence.pdf"),
            ])
            old_tasks = setup_env["vendor.invoice.import.task"].search([
                ("source_pdf_attachment_id", "in", old_sources.ids),
            ])
            old_attempts = setup_env[
                "vendor.invoice.import.parse.attempt"
            ].search([("task_id", "in", old_tasks.ids)])
            old_artifacts = setup_env[
                "vendor.invoice.import.page.artifact"
            ].search([("parse_attempt_id", "in", old_attempts.ids)])
            old_calls = setup_env[
                "vendor.invoice.import.provider.call"
            ].search([("parse_attempt_id", "in", old_attempts.ids)])
            old_evidence_attachments = (
                old_artifacts.mapped("image_attachment_id")
                | old_calls.mapped("raw_response_attachment_id")
            )
            old_tasks.unlink()
            (old_sources | old_evidence_attachments).unlink()
            setup_env["wd.ai.provider.config"].search([
                ("name", "=", "Durable Evidence DeepSeek"),
            ]).unlink()
            source = setup_env["ir.attachment"].create({
                "name": "durable-evidence.pdf",
                "type": "binary",
                "datas": base64.b64encode(b"%PDF-1.4"),
                "res_model": "vendor.invoice.import.task",
                "public": False,
            })
            provider = setup_env["wd.ai.provider.config"].create({
                "name": "Durable Evidence DeepSeek",
                "api_base_url": "https://example.invalid",
                "model_name": "durable-model",
            })
            task = setup_env["vendor.invoice.import.task"].create({
                "source_pdf_attachment_id": source.id,
                "selected_provider_config_id": provider.id,
                "state": "parsing",
            })
            attempt = setup_env[
                "vendor.invoice.import.parse.attempt"
            ].create({
                "task_id": task.id,
                "sequence": 1,
                "provider_config_id": provider.id,
                "status": "running",
            })
            setup_cr.commit()
            task_id = task.id
            attempt_id = attempt.id
            provider_id = provider.id

        with Registry(dbname).cursor() as caller_cr:
            caller_env = api.Environment(caller_cr, self.env.uid, {})
            attempt = caller_env[
                "vendor.invoice.import.parse.attempt"
            ].browse(attempt_id)
            provider = caller_env["wd.ai.provider.config"].browse(
                provider_id
            )
            with patch.object(
                observability_service,
                "config",
                {"test_enable": False},
            ):
                artifact_id = observability_service.persist_page_artifacts(
                    attempt,
                    [b"durable-png"],
                )[0]
                call_id = observability_service.begin_provider_call(
                    attempt,
                    artifact_id,
                    0,
                    provider,
                    {
                        "system": "system",
                        "user": "user",
                        "checksum": "checksum",
                    },
                )
                observability_service.finish_provider_call(
                    attempt,
                    call_id,
                    outcome="success",
                    validation_status="pass",
                    http_status=200,
                    raw_response=b'{"durable": true}',
                    page_extraction_result={"page_number": 1},
                    response_received=True,
                )
            caller_cr.rollback()

        with Registry(dbname).cursor() as check_cr:
            check_env = api.Environment(check_cr, self.env.uid, {})
            artifact = check_env[
                "vendor.invoice.import.page.artifact"
            ].browse(artifact_id).exists()
            provider_call = check_env[
                "vendor.invoice.import.provider.call"
            ].browse(call_id).exists()
            self.assertTrue(artifact)
            self.assertEqual(
                artifact.image_attachment_id.raw,
                b"durable-png",
            )
            self.assertTrue(provider_call)
            self.assertEqual(provider_call.outcome, "success")
            self.assertEqual(
                provider_call.raw_response_attachment_id.raw,
                b'{"durable": true}',
            )
            attachments = (
                artifact.image_attachment_id
                | provider_call.raw_response_attachment_id
                | check_env["vendor.invoice.import.task"]
                .browse(task_id).source_pdf_attachment_id
            )
            check_env["vendor.invoice.import.task"].browse(task_id).unlink()
            attachments.unlink()
            check_env["wd.ai.provider.config"].browse(provider_id).unlink()
            check_cr.commit()
