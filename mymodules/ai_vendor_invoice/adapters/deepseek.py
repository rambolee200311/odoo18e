# © 2024 Wukong Digital. License LGPL-3.

from openai import OpenAI

from .aibase import (
    BaseVisionAIProviderAdapter,
    EXTRACTION_CONTRACT_VERSION,
    PROMPT_VERSION,
    SYSTEM_PROMPT,
    USER_PROMPT,
)


class DeepSeekAIProviderAdapter(BaseVisionAIProviderAdapter):
    provider_name = "deepseek"
    provider_label = "DeepSeek"

    def _build_client(self, provider_config):
        return OpenAI(
            api_key=self._credentials(provider_config),
            base_url=provider_config.api_base_url,
            timeout=provider_config.http_timeout,
            max_retries=0,
        )

    def _build_payload(self, provider_config, images):
        payload = self._vision_payload(provider_config, images)
        payload.update({
            "reasoning_effort": "high",
            "extra_body": {"thinking": {"type": "enabled"}},
        })
        return payload


__all__ = [
    "DeepSeekAIProviderAdapter",
    "EXTRACTION_CONTRACT_VERSION",
    "PROMPT_VERSION",
    "SYSTEM_PROMPT",
    "USER_PROMPT",
]
