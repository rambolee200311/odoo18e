# © 2024 Wukong Digital. License LGPL-3.

import json
import hashlib
import logging

from jsonschema import ValidationError, validate
from openai import APIConnectionError, APIStatusError, APITimeoutError, OpenAI

from .aibase import BaseVisionAIProviderAdapter, PROMPT_VERSION
from .base import AIProviderPermanentError, AIProviderTemporaryError
from ..services.native_document_projection import document_to_canonical
from ..services import observability_service
from ..schemas.document_extraction import INVOICE_EXTRACTION_RESULT_SCHEMA


_logger = logging.getLogger(__name__)


class OpenAIAIProviderAdapter(BaseVisionAIProviderAdapter):
    provider_name = "openai"
    provider_label = "OpenAI"
    supported_input_modes = frozenset({"rendered_images", "native_pdf"})

    def _build_client(self, provider_config):
        return OpenAI(
            api_key=self._credentials(provider_config),
            base_url=provider_config.api_base_url,
            timeout=provider_config.http_timeout,
            max_retries=0,
        )

    def _build_payload(self, provider_config, images):
        return self._vision_payload(provider_config, images)

    def parse_pdf(self, provider_input, provider_config, max_attempt_retry=0, attempt_obj=None):
        if provider_input.get("mode", "rendered_images") == "native_pdf":
            document, raw_response, _content = self.parse_native_pdf(
                provider_input,
                provider_config,
                self._native_document_instructions(),
                attempt_obj,
            )
            try:
                canonical = document_to_canonical(document)
            except Exception as error:
                error.failure_stage = "CANONICAL_VALIDATION"
                raise
            return canonical, raw_response
        return super().parse_pdf(
            provider_input,
            provider_config,
            max_attempt_retry,
            attempt_obj,
        )

    @staticmethod
    def _native_document_instructions():
        return """Extract the supplied invoice as a document-level JSON object.
Return valid JSON only with document_type and invoice.lines. Keep one
independent invoice business record as one line; keep nested charge components
inside that record and do not create extra lines. When a line contains a
reconciliation clue, preserve it as reconciliation_clues with the original
label and value. Do not infer a clue type or match transport orders. Include
the invoice number, date, currency, totals, supplier, and tax values when
present."""

    def parse_native_pdf(
        self, provider_input, provider_config, instructions, attempt_obj=None
    ):
        """Call OpenAI native PDF transport without applying business normalization."""
        self.validate_input_mode(provider_input["mode"])
        document_bytes = provider_input["document_bytes"]
        client = self._build_client(provider_config)
        attempt = attempt_obj
        prompt_snapshot = {
            "prompt_version": PROMPT_VERSION,
            "instructions_checksum": hashlib.sha256(
                instructions.encode("utf-8")
            ).hexdigest(),
        }
        retries = 0
        while True:
            provider_call = observability_service.begin_provider_call(
                attempt,
                None,
                retries,
                provider_config,
                prompt_snapshot,
                input_page_count=provider_input.get("source", {}).get("page_count"),
                input_mode="native_pdf",
                input_document_type="application/pdf",
                rendered_image_count=0,
            ) if attempt else None
            try:
                uploaded_file = client.files.create(
                    file=("source.pdf", document_bytes, "application/pdf"),
                    purpose="user_data",
                    timeout=provider_config.http_timeout,
                )
                response = client.responses.create(
                    model=provider_config.model_name,
                    reasoning={"effort": "low"},
                    input=[{
                        "role": "user",
                        "content": [
                            {
                                "type": "input_file",
                                "file_id": uploaded_file.id,
                            },
                            {
                                "type": "input_text",
                                "text": instructions,
                            },
                        ],
                    }],
                    text={
                        "format": {
                            "type": "json_schema",
                            "name": "InvoiceExtractionResult",
                            "strict": True,
                            "schema": INVOICE_EXTRACTION_RESULT_SCHEMA,
                        },
                    },
                    stream=False,
                    timeout=provider_config.http_timeout,
                )
                raw_response = response.model_dump_json().encode("utf-8")
                content = response.output_text
                if not isinstance(content, str) or not content.strip():
                    error = AIProviderPermanentError(
                        "OpenAI native PDF structured output was missing."
                    )
                    error.failure_stage = "PAGE_SCHEMA_VALIDATION"
                    raise error
                try:
                    parsed = json.loads(content)
                    validate(parsed, INVOICE_EXTRACTION_RESULT_SCHEMA)
                except (json.JSONDecodeError, ValidationError) as error:
                    error.failure_stage = "PAGE_SCHEMA_VALIDATION"
                    raise AIProviderPermanentError(
                        "OpenAI native PDF structured output was invalid."
                    ) from error
                observability_service.finish_provider_call(
                    attempt,
                    provider_call,
                    outcome="success",
                    validation_status="not_run",
                    http_status=200,
                    raw_response=raw_response,
                    response_received=True,
                )
                return parsed, raw_response, content
            except (APITimeoutError, APIConnectionError) as error:
                self._finish_native_transport_failure(
                    attempt, provider_call, error, retries
                )
                if retries >= provider_config.max_internal_retry:
                    raise AIProviderTemporaryError(
                        "AI provider request temporarily unavailable."
                    ) from error
                self._wait_before_retry(retries)
                retries += 1
                observability_service.record_internal_retry(attempt, retries)
            except APIStatusError as error:
                self._finish_native_transport_failure(
                    attempt,
                    provider_call,
                    error,
                    retries,
                    http_status=error.status_code,
                    response_received=True,
                )
                if not self._is_retryable_http_status(error.status_code):
                    raise AIProviderPermanentError(
                        "AI provider rejected the request."
                    ) from error
                if retries >= provider_config.max_internal_retry:
                    raise AIProviderTemporaryError(
                        "AI provider temporarily unavailable."
                    ) from error
                self._wait_before_retry(retries)
                retries += 1
                observability_service.record_internal_retry(attempt, retries)
            except Exception as error:
                _logger.exception(
                    "OpenAI native PDF provider call failed: attempt=%s "
                    "exception=%s message=%s",
                    attempt.id if attempt else None,
                    type(error).__name__,
                    " ".join(str(error).split())[:500],
                )
                observability_service.finish_provider_call(
                    attempt,
                    provider_call,
                    outcome="failed",
                    validation_status="not_run",
                    failure_stage=getattr(
                        error, "failure_stage", "PAGE_PROVIDER_REQUEST"
                    ),
                    safe_error_summary="OpenAI native PDF request failed.",
                )
                raise

    def _finish_native_transport_failure(
        self,
        attempt,
        provider_call,
        error,
        retry_index,
        http_status=None,
        response_received=False,
    ):
        _logger.exception(
            "OpenAI native PDF provider transport failed: attempt=%s "
            "exception=%s retry_index=%s",
            attempt.id if attempt else None,
            type(error).__name__,
            retry_index,
        )
        observability_service.finish_provider_call(
            attempt,
            provider_call,
            outcome="failed" if response_received else "no_response",
            validation_status="not_run",
            http_status=http_status,
            failure_stage=(
                "PAGE_PROVIDER_RESPONSE" if response_received
                else "PAGE_PROVIDER_REQUEST"
            ),
            safe_error_summary=(
                "Provider returned an HTTP error."
                if response_received
                else "Provider request did not return a response."
            ),
            response_received=response_received,
        )
        if attempt:
            observability_service.record_provider_diagnostic(
                attempt,
                {
                    "input_mode": "native_pdf",
                    "retry_index": retry_index,
                    "http_status_code": http_status,
                    "exception_class": type(error).__name__,
                    "provider_error_category": (
                        self._status_category(http_status)
                        if http_status is not None
                        else (
                            "TEMPORARY_TIMEOUT"
                            if isinstance(error, APITimeoutError)
                            else "TEMPORARY_CONNECTION"
                        )
                    ),
                    "response_parse_status": "NOT_RUN",
                    "canonical_schema_status": "NOT_RUN",
                },
            )
