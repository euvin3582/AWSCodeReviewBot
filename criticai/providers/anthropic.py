"""Anthropic Claude provider via bedrock-runtime InvokeModel."""

from __future__ import annotations

import json

import botocore.session

from criticai.config import Config
from criticai.providers.base import ModelProvider


class AnthropicProvider(ModelProvider):
    """Invokes Anthropic Claude models through bedrock-runtime.

    Handles both bare model IDs and region-prefixed inference profile IDs.
    Only sends `temperature` (not `top_p`) to avoid the ValidationException
    on Claude 4.5+ models that reject both simultaneously.
    """

    def __init__(self, config: Config) -> None:
        self._config = config

    def invoke(self, model_id: str, system_prompt: str, user_content: str) -> str:
        session = botocore.session.get_session()
        session.set_credentials(
            access_key=self._config.aws_access_key_id,
            secret_key=self._config.aws_secret_access_key,
        )
        client = session.create_client(
            "bedrock-runtime", region_name=self._config.aws_region
        )

        request_body = json.dumps({
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": self._config.max_tokens,
            "temperature": self._config.temperature,
            "system": system_prompt,
            "messages": [{"role": "user", "content": user_content}],
        })

        response = client.invoke_model(
            modelId=model_id,
            contentType="application/json",
            accept="application/json",
            body=request_body,
        )

        response_body = b"".join(response["body"])
        response_json = json.loads(response_body.decode("utf-8", errors="ignore"))
        return response_json["content"][0]["text"]
