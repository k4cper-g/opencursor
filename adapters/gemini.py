"""Gemini adapter — Google Gemini 3 Flash via OpenRouter with XML prompting."""

from PIL import Image

from adapters.base import ModelAdapter, ModelResponse
from parsing import parse_response


class GeminiAdapter(ModelAdapter):
    name = "gemini"
    default_model_id = "google/gemini-3-flash-preview"
    default_base_url = "https://openrouter.ai/api/v1"

    def build_client(self, config: dict):
        return self._build_openrouter_client(config)

    def _call_api(self, client, system_prompt: str, user_text: str,
                  screenshot: Image.Image, config: dict) -> ModelResponse:
        messages = self._build_openai_messages(system_prompt, user_text, screenshot)

        resp = client.chat.completions.create(
            model=self._get_model_id(config),
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
