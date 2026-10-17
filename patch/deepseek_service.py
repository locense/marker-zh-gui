import json
import time
from typing import List

import PIL
from openai import APITimeoutError, RateLimitError
from pydantic import BaseModel

from marker.logger import get_logger
from marker.schema.blocks import Block
from marker.services.openai import OpenAIService

logger = get_logger()


class DeepSeekService(OpenAIService):
    """OpenAI-compatible service using DeepSeek's standard JSON Output mode.

    Marker normally requests OpenAI's structured-output response_format with a
    Pydantic schema. DeepSeek does not accept that response_format type, so we
    send the schema in the prompt and use {"type": "json_object"} instead.
    """

    def __call__(
        self,
        prompt: str,
        image: PIL.Image.Image | List[PIL.Image.Image] | None,
        block: Block | None,
        response_schema: type[BaseModel],
        max_retries: int | None = None,
        timeout: int | None = None,
    ):
        if max_retries is None:
            max_retries = self.max_retries
        if timeout is None:
            timeout = self.timeout

        client = self.get_client()
        image_data = self.format_image_for_llm(image)
        schema = response_schema.model_json_schema()
        json_prompt = (
            prompt
            + "\n\nReturn only valid JSON that conforms to this JSON schema:\n"
            + json.dumps(schema, ensure_ascii=False)
        )
        messages = [
            {
                "role": "user",
                "content": [
                    *image_data,
                    {"type": "text", "text": json_prompt},
                ],
            }
        ]

        total_tries = max_retries + 1
        for tries in range(1, total_tries + 1):
            try:
                response = client.chat.completions.create(
                    extra_headers={
                        "X-Title": "Marker",
                        "HTTP-Referer": "https://github.com/datalab-to/marker",
                    },
                    model=self.openai_model,
                    messages=messages,
                    timeout=timeout,
                    response_format={"type": "json_object"},
                )
                response_text = response.choices[0].message.content
                total_tokens = response.usage.total_tokens if response.usage else 0
                if block:
                    block.update_metadata(
                        llm_tokens_used=total_tokens, llm_request_count=1
                    )
                logger.info(
                    f"DeepSeek request succeeded, tokens={total_tokens}, model={self.openai_model}"
                )
                return json.loads(response_text)
            except (APITimeoutError, RateLimitError) as exc:
                if tries == total_tries:
                    logger.error(
                        f"DeepSeek rate limit error: {exc}. Max retries reached."
                    )
                    break
                wait_time = tries * self.retry_wait_time
                logger.warning(
                    f"DeepSeek rate limit error: {exc}. Retrying in {wait_time}s."
                )
                time.sleep(wait_time)
            except Exception as exc:
                logger.error(f"DeepSeek inference failed: {exc}")
                break
        return {}


