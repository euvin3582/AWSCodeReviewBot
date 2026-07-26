"""Amazon Titan provider via bedrock-runtime InvokeModel."""

from __future__ import annotations

import json

import botocore.session

from criticai.config import Config
from criticai.providers.base import ModelProvider


class AmazonProvider(ModelProvider):
    """Invokes Amazon Titan Text models through bedrock-runtime."""

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
            "inputText": system_prompt + user_content,
            "textGenerationConfig": {
                "temperature": self._config.temperature,
                "topP": self._config.top_p,
                "maxTokenCount": self._config.max_tokens,
            },
        })

        response = client.invoke_model(
            modelId=model_id,
            contentType="application/json",
            accept="application/json",
            body=request_body,
        )

        response_body = b"".join(response["body"])
        response_json = json.loads(response_body.decode("utf-8", errors="ignore"))

        error = response_json.get("error")
        if error is not None:
            raise RuntimeError(f"Titan text generation error: {error}")

        print(f"Input token count: {response_json['inputTextTokenCount']}")
        for result in response_json["results"]:
            print(f"Token count: {result['tokenCount']}")
            return result["outputText"]

        raise RuntimeError("Amazon Titan response contained no results")
