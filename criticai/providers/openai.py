"""OpenAI provider via bedrock-mantle Responses API.

OpenAI models on Bedrock (GPT-5.x) are NOT reachable through
bedrock-runtime — they use the separate bedrock-mantle endpoint which
speaks the OpenAI Responses API. Since there's no boto3 service model
for bedrock-mantle, requests are hand-signed with SigV4.
"""

from __future__ import annotations

import json

import botocore.session
from botocore.awsrequest import AWSRequest
from botocore.auth import SigV4Auth
import requests

from criticai.config import Config
from criticai.providers.base import ModelProvider


class OpenAIProvider(ModelProvider):
    """Invokes OpenAI models through the bedrock-mantle endpoint.

    Does not send temperature or top_p (GPT-5.6 Terra rejects them).
    Only sends max_output_tokens. If the model spends its entire budget
    on reasoning and returns no message text, raises so fallback fires.
    """

    def __init__(self, config: Config) -> None:
        self._config = config

    def invoke(self, model_id: str, system_prompt: str, user_content: str) -> str:
        session = botocore.session.get_session()
        session.set_credentials(
            access_key=self._config.aws_access_key_id,
            secret_key=self._config.aws_secret_access_key,
        )
        credentials = session.get_credentials().get_frozen_credentials()

        url = (
            f"https://bedrock-mantle.{self._config.aws_region}.api.aws"
            f"/openai/v1/responses"
        )
        body = json.dumps({
            "model": model_id,
            "input": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
            "max_output_tokens": self._config.max_tokens,
            "store": False,
        })

        # SigV4-sign the request (no boto3 service model for bedrock-mantle)
        aws_request = AWSRequest(
            method="POST",
            url=url,
            data=body,
            headers={"Content-Type": "application/json"},
        )
        SigV4Auth(credentials, "bedrock-mantle", self._config.aws_region).add_auth(
            aws_request
        )
        prepared = aws_request.prepare()

        response = requests.post(url, data=body, headers=dict(prepared.headers))
        response_json = response.json()

        if response.status_code >= 400 or response_json.get("error"):
            raise RuntimeError(
                f"bedrock-mantle error ({response.status_code}): "
                f"{response_json.get('error') or response.text}"
            )

        # Extract message text from the Responses API output
        message_items = [
            item
            for item in response_json.get("output", [])
            if item.get("type") == "message"
        ]
        if not message_items:
            raise RuntimeError(
                f"bedrock-mantle returned no message output "
                f"(status={response_json.get('status')!r}, "
                f"incomplete_details={response_json.get('incomplete_details')!r}); "
                f"increase max-tokens if due to reasoning-token overhead"
            )

        content = message_items[0].get("content", [])
        text_parts = [
            part.get("text", "")
            for part in content
            if part.get("type") == "output_text"
        ]
        result_text = "".join(text_parts).strip()
        if not result_text:
            raise RuntimeError(
                "bedrock-mantle message item contained no output_text content"
            )

        return result_text
