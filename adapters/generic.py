"""Generic adapter — any OpenAI-compatible endpoint with XML prompting."""

import sys

from PIL import Image

from adapters.base import ModelAdapter, ModelResponse
from parsing import parse_response


class GenericAdapter(ModelAdapter):
    name = "generic"
    default_base_url = "https://openrouter.ai/api/v1"

    def build_client(self, config: dict):
        return self._build_openrouter_client(config)

    def _call_api(self, client, system_prompt: str, user_text: str,
                  screenshot: Image.Image, config: dict) -> ModelResponse:
        model_id = self._get_model_id(config)
        if not model_id:
            sys.exit("--model-id is required when using the generic adapter (e.g. --model-id 'meta-llama/llama-4-maverick')")

        messages = self._build_openai_messages(system_prompt, user_text, screenshot)

        resp = client.chat.completions.create(
            model=model_id,
            messages=messages,
            max_tokens=config.get("max_tokens", 4096),
            temperature=config.get("temperature", 0),
        )

        choice = resp.choices[0]
        raw = choice.message.content.strip() if choice.message.content else ""

        self._print_debug(
            finish_reason=choice.finish_reason,
            usage=vars(resp.usage) if resp.usage else None,
            raw=raw,
        )

        parsed = parse_response(raw)
        return self._build_response(raw, parsed, self._openai_usage_dict(resp.usage))

    def get_prompt_overrides(self) -> dict:
        return {"coordinate_instructions": "xml_box"}
