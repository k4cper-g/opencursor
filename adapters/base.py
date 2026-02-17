"""Abstract base class for model adapters and shared types."""

from __future__ import annotations

import os
import sys
import time
from abc import ABC, abstractmethod
from typing import Any, TypedDict

from PIL import Image

from screenshot import encode_image


class ModelResponse(TypedDict):
    raw: str
    parsed: dict
    think: str | None
    usage: dict | None


class ModelAdapter(ABC):
    """Base class all model adapters must extend.

    Subclasses must implement:
        - name (class attribute)
        - build_client(config)
        - _call_api(client, system_prompt, user_text, screenshot, config)
        - get_prompt_overrides()
    """

    name: str

    @abstractmethod
    def build_client(self, config: dict) -> Any:
        """Create and return an API client."""
        ...

    @abstractmethod
    def _call_api(self, client: Any, system_prompt: str, user_text: str,
                  screenshot: Image.Image, config: dict) -> ModelResponse:
        """Make the actual API call and return a parsed response.

        Subclasses should use the helper methods below to reduce boilerplate.
        """
        ...

    @abstractmethod
    def get_prompt_overrides(self) -> dict:
        """Return model-specific prompt template overrides."""
        ...

    def call(self, client: Any, system_prompt: str, user_text: str,
             screenshot: Image.Image, config: dict) -> ModelResponse:
        """Call the model with automatic retry on rate limits.

        This is the public entry point called by the agent loop.
        Subclasses implement _call_api() instead.
        """
        last_error = None
        for attempt in range(3):
            try:
                return self._call_api(client, system_prompt, user_text, screenshot, config)
            except Exception as e:
                if self._is_rate_limit(e):
                    last_error = e
                    wait = 2 ** (attempt + 1)  # 2s, 4s, 8s
                    print(f"Rate limited (attempt {attempt + 1}/3), waiting {wait}s...")
                    time.sleep(wait)
                else:
                    raise

        sys.exit(f"Aborted: rate limited after 3 retries ({last_error})")

    # -- Helper methods for subclasses --

    def _is_rate_limit(self, error: Exception) -> bool:
        """Check if an exception is a rate limit error. Override for custom logic."""
        # Works for openai.RateLimitError
        if type(error).__name__ == "RateLimitError":
            return True
        # Fallback: check message for rate/overload keywords
        msg = str(error).lower()
        return "rate" in msg or "overloaded" in msg

    def _get_model_id(self, config: dict) -> str:
        """Get the model ID from config, falling back to adapter default."""
        return config.get("model_id") or getattr(self, "default_model_id", None) or ""

    def _build_openrouter_client(self, config: dict):
        """Build an OpenAI client pointed at OpenRouter. Used by Qwen, Gemini, Generic."""
        from openai import OpenAI

        api_key = os.getenv(config.get("api_key_env", "OPENROUTER_API_KEY"))
        if not api_key:
            sys.exit(f"{config.get('api_key_env', 'OPENROUTER_API_KEY')} not set in .env")
        return OpenAI(
            base_url=config.get("base_url") or getattr(self, "default_base_url", "https://openrouter.ai/api/v1"),
            api_key=api_key,
            timeout=120,
            default_headers={
                "HTTP-Referer": "https://github.com/opencursor",
                "X-Title": "opencursor-agent",
            },
        )

    def _build_openai_messages(self, system_prompt: str, user_text: str,
                               screenshot: Image.Image) -> list[dict]:
        """Build the standard OpenAI-format message array with screenshot."""
        return [
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{encode_image(screenshot)}"}},
                    {"type": "text", "text": user_text},
                ],
            },
        ]

    def _print_debug(self, *, finish_reason: str = None, usage: dict = None,
                     reasoning: str = None, raw: str = None,
                     tool_calls: list = None, extra_lines: list[str] = None):
        """Print standardized debug output."""
        print(f"\n--- DEBUG ---")
        if finish_reason:
            print(f"Finish reason: {finish_reason}")
        if usage:
            labels = usage
            if "prompt_tokens" in labels:
                print(f"Tokens — prompt: {labels['prompt_tokens']}, completion: {labels['completion_tokens']}, total: {labels['total_tokens']}")
            elif "input_tokens" in labels:
                print(f"Tokens — input: {labels['input_tokens']}, output: {labels['output_tokens']}")
        if reasoning:
            print(f"Hidden reasoning ({len(reasoning)} chars):\n{reasoning}")
        if tool_calls:
            print(f"Tool calls: {len(tool_calls)}")
            for tc in tool_calls:
                print(f"  {tc.get('name', '?')}: {tc.get('input', tc.get('arguments', ''))}")
        if raw is not None:
            print(f"Response length: {len(raw)} chars")
            print(f"Full response:\n{raw}")
        if extra_lines:
            for line in extra_lines:
                print(line)
        print(f"--- END DEBUG ---\n")

    def _extract_think(self, parsed: dict) -> str | None:
        """Extract think text from a parsed response dict."""
        think = parsed.get("think")
        if think:
            return think
        if parsed.get("type") == "single":
            return parsed.get("action", {}).get("think")
        return None

    def _build_response(self, raw: str, parsed: dict, usage: dict | None) -> ModelResponse:
        """Package raw output, parsed actions, and usage into a ModelResponse."""
        return {
            "raw": raw,
            "parsed": parsed,
            "think": self._extract_think(parsed),
            "usage": usage,
        }

    def _openai_usage_dict(self, usage) -> dict | None:
        """Convert an OpenAI usage object to a plain dict."""
        if not usage:
            return None
        return {
            "prompt": usage.prompt_tokens,
            "completion": usage.completion_tokens,
            "total": usage.total_tokens,
        }
