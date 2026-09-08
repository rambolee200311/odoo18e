# © 2024 Wukong Digital. License LGPL-3.
"""Provider adapters.  Adapters never expose provider secrets in exceptions."""

from abc import ABC, abstractmethod
from datetime import date, datetime
from decimal import Decimal
import copy
import time

import requests
from jsonschema import ValidationError as JSONSchemaValidationError
from jsonschema import validate

from ..schemas.canonical import CANONICAL_INVOICE_RESULT_SCHEMA


class AIProviderError(Exception):
    """Base class for errors returned by an AI provider."""


class AIProviderTemporaryError(AIProviderError):
    """The request may succeed when retried later."""


class AIProviderPermanentError(AIProviderError):
    """The request cannot succeed without changing its input/configuration."""


class BaseAIProviderAdapter(ABC):
    provider_name = None
    supported_input_modes = frozenset()

    def __init__(self, env):
        self.env = env

    def _credentials(self, provider_config):
        # Reading the key through sudo is intentional; callers still cannot
        # return it through an RPC recordset.
        return provider_config.sudo().api_key

    def validate_input_mode(self, mode):
        if mode not in self.supported_input_modes:
            error = AIProviderPermanentError(
                "Configured document input mode is not supported by this provider."
            )
            error.failure_stage = "INPUT_STRATEGY"
            raise error

    @staticmethod
    def _wait_before_retry(retry_index):
        time.sleep(2 if retry_index == 0 else 5)

    @staticmethod
    def _is_retryable_http_status(status_code):
        return status_code in (408, 429, 500, 502, 503, 504)

    def _request(
        self,
        provider_config,
        payload,
        headers=None,
        max_attempt_retry=0,
        attempt_obj=None,
        endpoint=None,
    ):
        request_headers = {"Content-Type": "application/json"}
        if headers:
            request_headers.update(headers)
        retries = 0
        while True:
            try:
                response = requests.post(
                    endpoint or provider_config.api_base_url,
                    json=payload,
                    headers=request_headers,
                    timeout=provider_config.http_timeout,
                )
            except (requests.Timeout, requests.ConnectionError) as error:
                if retries < max_attempt_retry:
                    self._wait_before_retry(retries)
                    retries += 1
                    if attempt_obj:
                        attempt_obj.write({"attempt_internal_retry_count": retries})
                    continue
                raise AIProviderTemporaryError("AI provider request temporarily unavailable.") from error
            except requests.RequestException as error:
                raise AIProviderPermanentError("AI provider request failed.") from error
            if self._is_retryable_http_status(response.status_code):
                if retries < max_attempt_retry:
                    self._wait_before_retry(retries)
                    retries += 1
                    if attempt_obj:
                        attempt_obj.write({"attempt_internal_retry_count": retries})
                    continue
                raise AIProviderTemporaryError("AI provider temporarily unavailable.")
            break
        if response.status_code >= 400:
            raise AIProviderPermanentError("AI provider rejected the request.")
        try:
            body = response.json()
        except ValueError as error:
            raise AIProviderPermanentError("AI provider returned invalid JSON.") from error
        return body, response.content

    @staticmethod
    def _canonical(body):
        if not isinstance(body, dict):
            raise AIProviderPermanentError("AI provider returned an invalid invoice result.")
        result = body.get("canonical_result", body.get("result", body))
        if not isinstance(result, dict):
            raise AIProviderPermanentError("AI provider returned an invalid invoice result.")
        normalized = _normalize_canonical_result(result)
        try:
            validate(normalized, CANONICAL_INVOICE_RESULT_SCHEMA)
        except JSONSchemaValidationError as error:
            raise AIProviderPermanentError(
                "AI provider returned an invalid invoice schema."
            ) from error
        return normalized

    @abstractmethod
    def parse_pdf(self, provider_input, provider_config, max_attempt_retry=0, attempt_obj=None):
        """Return ``(canonical_result, raw_response_bytes)``."""


def adapter_for(env, provider_config):
    from .claude import ClaudeAIProviderAdapter
    from .deepseek import DeepSeekAIProviderAdapter
    from .openai import OpenAIAIProviderAdapter

    name = (provider_config.name or "").lower()
    if "claude" in name or "anthropic" in name:
        return ClaudeAIProviderAdapter(env)
    if "deepseek" in name:
        return DeepSeekAIProviderAdapter(env)
    if "openai" in name:
        return OpenAIAIProviderAdapter(env)
    raise AIProviderPermanentError("Unsupported AI provider.")


_AMOUNT_FIELDS = {"total_amount", "total_tax", "amount"}
_TEXT_FIELDS = {
    "invoice_number",
    "supplier_raw_text",
    "currency_raw_text",
    "description",
    "tax_raw_text",
}


def _normalize_canonical_result(result):
    """Normalize provider scalar values without applying business rules."""
    normalized = copy.deepcopy(result)
    for section_name, section in normalized.items():
        if section_name == "header" and isinstance(section, dict):
            _normalize_fields(section)
        elif section_name == "lines" and isinstance(section, list):
            for line in section:
                if isinstance(line, dict):
                    _normalize_fields(line)
    return normalized


def _normalize_fields(values):
    for field_name, field in values.items():
        if not isinstance(field, dict) or "value" not in field:
            continue
        value = field["value"]
        if value is None:
            continue
        if field_name in _AMOUNT_FIELDS:
            field["value"] = str(value)
        elif field_name == "invoice_date":
            if isinstance(value, (date, datetime)):
                field["value"] = value.isoformat()
            else:
                field["value"] = str(value).strip()
        elif field_name in _TEXT_FIELDS:
            field["value"] = str(value).strip()
