# © 2024 Wukong Digital. License LGPL-3.
import base64
import copy
import hashlib
import json
import logging
import time
from datetime import datetime, timezone

from openai import (
    APIError,
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
)
from jsonschema import ValidationError, validate

from .base import (
    AIProviderPermanentError,
    AIProviderTemporaryError,
    BaseAIProviderAdapter,
)
from ..schemas.page_extraction import PAGE_EXTRACTION_RESULT_SCHEMA
from .document_normalizer import (
    DocumentNormalizationError,
    normalize_page_results,
)

_logger = logging.getLogger(__name__)

EXTRACTION_CONTRACT_VERSION = "transport-invoice-page-v1"
PROMPT_VERSION = "vision-extraction-v1.3"

SYSTEM_PROMPT = """You are a transport-supplier-invoice fact extractor, not a business decision maker.
Extract only facts visibly printed on the supplied PDF pages. Return JSON only.
Return exactly one JSON object with a pages array. The pages array must contain exactly one
PageExtractionResult for every supplied image, in image order, with page_number 1..N.
The top-level object may contain ONLY the key pages; these are the only keys
allowed at the top level. The object contains only these keys at the top level.
Example envelope: {"pages": [{"page_number": 1, "header": {}, "lines": [], "raw_facts": []}]}
Do not add any other top-level keys. Use this exact structure:
{
  "page_number": 1,
  "header": {"field_name": "string, number, or null"},
  "lines": [
    {"field_name": "string, number, or null",
     "raw_fields": [{"source_label": "printed label", "source_value": "value"}]}
  ],
  "raw_facts": [{"source_label": "printed label", "source_value": "value"}]
}
Header field values and line field values must be scalar string, number, or null.
raw_fields and raw_facts are arrays of objects with exactly source_label and source_value.
Each page must include its page_number; do not add sender, receiver, invoice_header,
invoice_lines, totals, or any other top-level property.
Extract explicit invoice header fields, fee and charge lines, dates, addresses,
and explicitly labelled identifiers or references. Preserve every uncertain or
unclassified printed field in raw_facts using its original source_label and
source_value. Do not determine business meaning unless the printed label
explicitly states it.

Do not guess, autocomplete, calculate, reconcile, or fill missing values.
Omit missing fields or use null. Do not use information from another page.
Do not treat repeated headers, footers, or column headings as invoice lines.
Do not interpret Shipment Number, Dossier, O.No., Opdracht, Uw ref., Your reference,
customer reference, order reference, transport reference, booking
reference, or consignment reference as invoice_number unless the page explicitly
labels the value as an invoice number.
Use plain scalar values and return no explanation outside the JSON object."""

USER_PROMPT = """Extract visible facts from all supplied PDF pages and return one document envelope.
Each item in pages is a PageExtractionResult with page_number, header, lines,
and raw_facts.
Return exactly one JSON object with only this top-level key: pages.
Return exactly one PageExtractionResult per supplied image, in order, numbered 1 through N.
Use header for header facts, lines for fee/charge line objects, and raw_facts for
uncertain printed facts. Header and line values must be scalar string, number, or null.
Each raw_facts item must contain exactly source_label and source_value.
Include explicit invoice header fields, fee or charge lines, dates, addresses,
and explicitly labelled identifiers or references. Keep standard fields as plain
scalar values. For every visible field whose business meaning is uncertain, add
a raw_facts item containing the original source_label and source_value.
Do not classify or rename an uncertain reference. Do not convert shipment,
dossier, order, opdracht, customer, transport, or other reference numbers into
invoice_number unless the printed label explicitly says invoice number.
Do not guess, calculate, reconcile, autocomplete, or fill missing values.
Return JSON only."""

__all__ = [
    "BaseVisionAIProviderAdapter",
    "EXTRACTION_CONTRACT_VERSION",
    "PROMPT_VERSION",
    "SYSTEM_PROMPT",
    "USER_PROMPT",
]


def _with_failure_stage(error, failure_stage):
    error.failure_stage = failure_stage
    return error


class BaseVisionAIProviderAdapter(BaseAIProviderAdapter):
    """Shared multi-page vision extraction and provider-call observability."""

    provider_label = "AI provider"
    supported_input_modes = frozenset({"rendered_images"})

    def _build_client(self, provider_config):
        raise NotImplementedError

    def _build_payload(self, provider_config, images):
        raise NotImplementedError

    @staticmethod
    def _vision_payload(provider_config, images):
        return {
            "model": provider_config.model_name,
            "messages": [
                {
                    "role": "system",
                    "content": SYSTEM_PROMPT,
                },
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": USER_PROMPT,
                        },
                        *[
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": "data:image/png;base64,%s"
                                    % base64.b64encode(image).decode(),
                                },
                            }
                            for image in images
                        ],
                    ],
                },
            ],
            "stream": False,
            "response_format": {"type": "json_object"},
        }

    def parse_pdf(self, provider_input, provider_config, max_attempt_retry=0, attempt_obj=None):
        client = self._build_client(provider_config)
        images = provider_input["images"]
        page_artifacts = provider_input.get("page_artifacts", [])
        results, raw = self._parse_page_batch(
            client, provider_config, images, max_attempt_retry, attempt_obj,
            0, len(images), page_artifacts,
        )
        if isinstance(results, dict):
            results = [results]
        merge_started = time.monotonic()
        try:
            merged = normalize_page_results(results)
        except DocumentNormalizationError:
            self._log_diagnostic(
                attempt_obj,
                0,
                len(images),
                len(images),
                sum(len(image) for image in images),
                int((time.monotonic() - merge_started) * 1000),
                0,
                None,
                "AIProviderPermanentError",
                "DOCUMENT_NORMALIZATION_INVALID",
                "NOT_RUN",
                "PASS",
            )
            raise
        return merged, base64.b64encode(raw.encode() if isinstance(raw, str) else raw)

    def _parse_page_batch(
        self,
        client,
        provider_config,
        images,
        max_attempt_retry,
        attempt_obj,
        page_start,
        total_pages,
        page_artifact=None,
    ):
        payload = self._build_payload(provider_config, images)
        prompt_components = {
            "system": SYSTEM_PROMPT,
            "user": USER_PROMPT,
            "prompt_version": PROMPT_VERSION,
        }
        effective_prompt_snapshot = {
            **prompt_components,
            "checksum": hashlib.sha256(
                json.dumps(
                    prompt_components,
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode("utf-8")
            ).hexdigest(),
        }
        retries = 0
        image_bytes = sum(len(image) for image in images)
        while True:
            from ..services import observability_service

            request_started = time.monotonic()
            started_at = datetime.now(timezone.utc).isoformat()
            provider_call = observability_service.begin_provider_call(
                attempt_obj,
                page_artifact,
                retries,
                provider_config,
                effective_prompt_snapshot,
                input_page_count=len(images),
                input_mode=provider_input.get("mode", "rendered_images"),
                input_document_type=(
                    "image/png"
                    if provider_input.get("mode", "rendered_images") == "rendered_images"
                    else provider_input.get("source", {}).get("mime_type")
                ),
                rendered_image_count=len(images),
            ) if attempt_obj else None
            try:
                response = client.chat.completions.create(**payload)
                elapsed_ms = int((time.monotonic() - request_started) * 1000)
                body = response.model_dump()
                raw = response.model_dump_json()
                content = body.get("choices", [{}])[0].get("message", {}).get("content")
                if not isinstance(content, str) or not content.strip():
                    observability_service.finish_provider_call(
                        attempt_obj,
                        provider_call,
                        outcome="response_invalid",
                        validation_status="not_run",
                        http_status=200,
                        raw_response=raw,
                        failure_stage="PAGE_PROVIDER_RESPONSE",
                        safe_error_summary="Provider response content was empty.",
                        response_received=True,
                    )
                    self._log_diagnostic(
                        attempt_obj, page_start, total_pages, len(images),
                        image_bytes, elapsed_ms, retries, 200, None,
                        "RESPONSE_EMPTY", "NOT_RUN", "FAIL", started_at,
                    )
                    raise _with_failure_stage(
                        AIProviderPermanentError(
                            f"{self.provider_label} response did not contain JSON "
                            "message content."
                        ),
                        "PAGE_PROVIDER_RESPONSE",
                    )
                try:
                    parsed_content = json.loads(content)
                except (TypeError, ValueError) as error:
                    observability_service.finish_provider_call(
                        attempt_obj,
                        provider_call,
                        outcome="response_invalid",
                        validation_status="not_run",
                        http_status=200,
                        raw_response=raw,
                        failure_stage="PAGE_PROVIDER_RESPONSE",
                        safe_error_summary="Provider response was not valid JSON.",
                        response_received=True,
                    )
                    self._log_diagnostic(
                        attempt_obj, page_start, total_pages, len(images),
                        image_bytes, elapsed_ms, retries, 200,
                        type(error).__name__, "RESPONSE_INVALID_JSON", "NOT_RUN",
                        "FAIL", started_at,
                    )
                    raise _with_failure_stage(
                        AIProviderPermanentError(
                            f"{self.provider_label} response did not contain valid JSON."
                        ),
                        "PAGE_PROVIDER_RESPONSE",
                    ) from error
                try:
                    result = self._document_extraction(
                        parsed_content, len(images)
                    )
                except (AIProviderPermanentError, ValidationError, TypeError, ValueError) as error:
                    observability_service.finish_provider_call(
                        attempt_obj,
                        provider_call,
                        outcome="response_invalid",
                        validation_status="fail",
                        http_status=200,
                        raw_response=raw,
                        failure_stage="PAGE_SCHEMA_VALIDATION",
                        safe_error_summary=                        "Document page extraction schema validation failed.",
                        response_received=True,
                        returned_page_count=(
                            len(parsed_content.get("pages", []))
                            if isinstance(parsed_content, dict)
                            and isinstance(parsed_content.get("pages"), list)
                            else 0
                        ),
                        failure_page_no=getattr(error, "failure_page_no", None),
                    )
                    self._log_diagnostic(
                        attempt_obj, page_start, total_pages, len(images),
                        image_bytes, elapsed_ms, retries, 200, type(error).__name__,
                        "RESPONSE_SCHEMA_INVALID", "FAIL", "PASS", started_at,
                    )
                    error.failure_stage = "PAGE_SCHEMA_VALIDATION"
                    raise
                observability_service.finish_provider_call(
                    attempt_obj,
                    provider_call,
                    outcome="success",
                    validation_status="pass",
                    http_status=200,
                    raw_response=raw,
                    page_extraction_result=(
                        result[0] if len(result) == 1 else {"pages": result}
                    ),
                    returned_page_count=len(result),
                    response_received=True,
                )
                self._log_diagnostic(
                    attempt_obj, page_start, total_pages, len(images), image_bytes,
                    elapsed_ms, retries, 200, None, "NONE", "PASS", "PASS",
                    started_at,
                )
                break
            except (APITimeoutError, APIConnectionError) as error:
                elapsed_ms = int((time.monotonic() - request_started) * 1000)
                category = (
                    "TEMPORARY_TIMEOUT"
                    if isinstance(error, APITimeoutError)
                    else "TEMPORARY_CONNECTION"
                )
                self._log_diagnostic(
                    attempt_obj, page_start, total_pages, len(images), image_bytes,
                    elapsed_ms, retries, None, type(error).__name__, category,
                    "NOT_RUN", "NOT_RUN", started_at,
                )
                observability_service.finish_provider_call(
                    attempt_obj,
                    provider_call,
                    outcome="no_response",
                    validation_status="not_run",
                    failure_stage="PAGE_PROVIDER_REQUEST",
                    safe_error_summary="Provider request did not return a response.",
                )
                if retries >= max_attempt_retry:
                    raise _with_failure_stage(
                        AIProviderTemporaryError(
                            "AI provider request temporarily unavailable."
                        ),
                        "PAGE_PROVIDER_REQUEST",
                    )
                self._wait_before_retry(retries)
                retries += 1
                observability_service.record_internal_retry(attempt_obj, retries)
            except APIStatusError as error:
                elapsed_ms = int((time.monotonic() - request_started) * 1000)
                category = self._status_category(error.status_code)
                self._log_diagnostic(
                    attempt_obj, page_start, total_pages, len(images), image_bytes,
                    elapsed_ms, retries, error.status_code, type(error).__name__,
                    category, "NOT_RUN", "NOT_RUN", started_at,
                )
                error_response = getattr(error, "response", None)
                observability_service.finish_provider_call(
                    attempt_obj,
                    provider_call,
                    outcome="failed",
                    validation_status="not_run",
                    http_status=error.status_code,
                    raw_response=getattr(error_response, "content", None),
                    failure_stage="PAGE_PROVIDER_RESPONSE",
                    safe_error_summary="Provider returned an HTTP error.",
                    response_received=True,
                )
                if self._is_retryable_http_status(error.status_code):
                    if retries < max_attempt_retry:
                        self._wait_before_retry(retries)
                        retries += 1
                        observability_service.record_internal_retry(
                            attempt_obj,
                            retries,
                        )
                        continue
                    raise _with_failure_stage(
                        AIProviderTemporaryError(
                            "AI provider temporarily unavailable."
                        ),
                        "PAGE_PROVIDER_RESPONSE",
                    ) from error
                raise _with_failure_stage(
                    AIProviderPermanentError(
                        "AI provider rejected the request."
                    ),
                    "PAGE_PROVIDER_RESPONSE",
                ) from error
            except APIError as error:
                elapsed_ms = int((time.monotonic() - request_started) * 1000)
                self._log_diagnostic(
                    attempt_obj, page_start, total_pages, len(images), image_bytes,
                    elapsed_ms, retries, None, type(error).__name__,
                    "UNKNOWN_PROVIDER_ERROR", "NOT_RUN", "NOT_RUN", started_at,
                )
                observability_service.finish_provider_call(
                    attempt_obj,
                    provider_call,
                    outcome="no_response",
                    validation_status="not_run",
                    failure_stage="PAGE_PROVIDER_REQUEST",
                    safe_error_summary="Provider request failed.",
                )
                raise _with_failure_stage(
                    AIProviderPermanentError(
                        "AI provider request failed."
                    ),
                    "PAGE_PROVIDER_REQUEST",
                ) from error
        return result, raw

    @staticmethod
    def _page_extraction(body, page_number):
        if not isinstance(body, dict):
            raise TypeError("Page extraction must be an object.")
        result = copy.deepcopy(body)
        result["page_number"] = page_number
        validate(result, PAGE_EXTRACTION_RESULT_SCHEMA)
        for fact in result.get("raw_facts", []):
            fact["source_page"] = page_number
        for line in result.get("lines", []):
            for fact in line.get("raw_fields", []):
                fact["source_page"] = page_number
        return result

    @classmethod
    def _document_extraction(cls, body, page_count):
        """Validate the provider envelope before any document normalization."""
        if not isinstance(body, dict) or set(body) != {"pages"}:
            raise ValidationError("Response must contain only a pages envelope.")
        pages = body["pages"]
        if not isinstance(pages, list) or len(pages) != page_count:
            error = ValueError("Response page count does not match input images.")
            error.failure_page_no = None
            raise error
        extracted = []
        for expected, page in enumerate(pages, start=1):
            try:
                if not isinstance(page, dict) or page.get("page_number") != expected:
                    error = ValueError("Response pages are not ordered and unique.")
                    error.failure_page_no = (
                        page.get("page_number") if isinstance(page, dict) else expected
                    )
                    raise error
                extracted.append(cls._page_extraction(page, expected))
            except (ValidationError, TypeError, ValueError) as error:
                if not hasattr(error, "failure_page_no"):
                    error.failure_page_no = expected
                raise
        return extracted

    @staticmethod
    def _status_category(status_code):
        if not isinstance(status_code, int):
            return "UNKNOWN_PROVIDER_ERROR"
        if status_code == 401 or status_code == 403:
            return "PERMANENT_AUTH"
        if status_code == 408:
            return "TEMPORARY_TIMEOUT"
        if status_code == 413:
            return "PERMANENT_UNSUPPORTED_INPUT"
        if status_code == 429:
            return "TEMPORARY_RATE_LIMIT"
        if status_code >= 500:
            return "TEMPORARY_5XX"
        if 400 <= status_code < 500:
            return "PERMANENT_BAD_REQUEST"
        return "UNKNOWN_PROVIDER_ERROR"

    @staticmethod
    def _log_diagnostic(
        attempt_obj,
        page_start,
        total_pages,
        image_count,
        total_image_bytes,
        elapsed_ms,
        retry_index,
        http_status_code,
        exception_class,
        provider_error_category,
        canonical_schema_status,
        response_parse_status,
        started_at=None,
    ):
        diagnostic = {
            "started_at": started_at or datetime.now(timezone.utc).isoformat(),
            "page_start": page_start + 1,
            "page_end": page_start + image_count,
            "page_count": image_count,
            "total_pages": total_pages,
            "image_count": image_count,
            "total_image_bytes": total_image_bytes,
            "elapsed_ms": elapsed_ms,
            "retry_index": retry_index,
            "http_status_code": http_status_code,
            "exception_class": exception_class,
            "provider_error_category": provider_error_category,
            "response_parse_status": response_parse_status,
            "canonical_schema_status": canonical_schema_status,
        }
        if attempt_obj:
            from ..services import observability_service

            observability_service.record_provider_diagnostic(
                attempt_obj,
                diagnostic,
            )
        _logger.info(
            "provider_page_diagnostic task_id=%s attempt_id=%s "
            "page_start=%s page_end=%s batch_page_count=%s total_pages=%s "
            "image_count=%s total_image_bytes=%s response_elapsed_ms=%s retry_index=%s "
            "http_status_code=%s exception_class=%s provider_error_category=%s "
            "response_parse_status=%s canonical_schema_status=%s",
            attempt_obj.task_id.id if attempt_obj else None,
            attempt_obj.id if attempt_obj else None,
            page_start + 1,
            page_start + image_count,
            image_count,
            total_pages,
            image_count,
            total_image_bytes,
            elapsed_ms,
            retry_index,
            http_status_code,
            exception_class,
            provider_error_category,
            response_parse_status,
            canonical_schema_status,
        )
