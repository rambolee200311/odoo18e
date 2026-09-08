# © 2024 Wukong Digital. License LGPL-3
import base64

from .base import BaseAIProviderAdapter


class ClaudeAIProviderAdapter(BaseAIProviderAdapter):
    provider_name = "claude"
    supported_input_modes = frozenset({"rendered_images"})

    def parse_pdf(self, provider_input, provider_config, max_attempt_retry=0, attempt_obj=None):
        payload = {
            "model": provider_config.model_name,
            "max_tokens": 8192,
            "messages": [{
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": "image/png",
                            "data": base64.b64encode(image).decode(),
                        },
                    }
                    for image in provider_input["images"]
                ],
            }],
        }
        headers = {
            "x-api-key": self._credentials(provider_config),
            "anthropic-version": "2023-06-01",
        }
        body, raw = self._request(
            provider_config, payload, headers, max_attempt_retry, attempt_obj
        )
        return self._canonical(body), raw
