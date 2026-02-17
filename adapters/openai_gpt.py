"""GPT-4o adapter — OpenAI API with tool_use for structured actions."""

import os
import sys

from PIL import Image

from adapters.base import ModelAdapter, ModelResponse, StreamCallback
from parsing import parse_response, parse_response_tool_use
from screenshot import encode_image

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "click",
            "description": "Left-click on a UI element",
            "parameters": {
                "type": "object",
                "properties": {
                    "target": {"type": "string", "description": "Description of the element to click"},
                    "x": {"type": "integer", "description": "X coordinate (0-1000 normalized, left=0 right=1000)"},
                    "y": {"type": "integer", "description": "Y coordinate (0-1000 normalized, top=0 bottom=1000)"},
                },
                "required": ["target", "x", "y"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "double_click",
            "description": "Double-click on a UI element",
            "parameters": {
                "type": "object",
                "properties": {
                    "target": {"type": "string", "description": "Description of the element"},
                    "x": {"type": "integer", "description": "X coordinate (0-1000)"},
                    "y": {"type": "integer", "description": "Y coordinate (0-1000)"},
                },
                "required": ["target", "x", "y"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "right_click",
            "description": "Right-click on a UI element",
            "parameters": {
                "type": "object",
                "properties": {
                    "target": {"type": "string", "description": "Description of the element"},
                    "x": {"type": "integer", "description": "X coordinate (0-1000)"},
                    "y": {"type": "integer", "description": "Y coordinate (0-1000)"},
                },
                "required": ["target", "x", "y"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "type",
            "description": "Type text at the current cursor position",
            "parameters": {
                "type": "object",
                "properties": {
                    "text": {"type": "string", "description": "The text to type"},
                },
                "required": ["text"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "hotkey",
            "description": "Press a keyboard shortcut (e.g. ctrl+c, alt+f4, enter)",
            "parameters": {
                "type": "object",
                "properties": {
                    "keys": {"type": "string", "description": "Keys separated by + (e.g. ctrl+shift+s)"},
                },
                "required": ["keys"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "scroll",
            "description": "Scroll the mouse wheel",
            "parameters": {
                "type": "object",
                "properties": {
                    "direction": {"type": "string", "enum": ["up", "down", "left", "right"]},
                    "amount": {"type": "integer", "description": "Number of scroll clicks (default 3)"},
                },
                "required": ["direction"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "drag",
            "description": "Drag from one point to another",
            "parameters": {
                "type": "object",
                "properties": {
                    "from_x": {"type": "integer", "description": "Start X (0-1000)"},
                    "from_y": {"type": "integer", "description": "Start Y (0-1000)"},
                    "to_x": {"type": "integer", "description": "End X (0-1000)"},
                    "to_y": {"type": "integer", "description": "End Y (0-1000)"},
                },
                "required": ["from_x", "from_y", "to_x", "to_y"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "wait",
            "description": "Pause before the next action",
            "parameters": {
                "type": "object",
                "properties": {
                    "seconds": {"type": "number", "description": "Seconds to wait (default 1)"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "done",
            "description": "Signal that the goal has been accomplished",
            "parameters": {
                "type": "object",
                "properties": {
                    "reason": {"type": "string", "description": "Why the task is complete"},
                },
                "required": ["reason"],
            },
        },
    },
]


class OpenAIGPTAdapter(ModelAdapter):
    name = "gpt4o"
    default_model_id = "gpt-4o"

    # Pricing: $2.50 input / $10.00 output per 1M tokens (Feb 2025)
    # https://platform.openai.com/docs/pricing
    pricing = {"input": 2.50, "output": 10.00}  # $/1M tokens

    def build_client(self, config: dict):
        from openai import OpenAI

        api_key = os.getenv(config.get("api_key_env", "OPENAI_API_KEY"))
        if not api_key:
            # Fall back to OPENROUTER if using OpenRouter base URL
            if config.get("base_url") and "openrouter" in config["base_url"]:
                api_key = os.getenv("OPENROUTER_API_KEY")
            if not api_key:
                sys.exit("OPENAI_API_KEY (or OPENROUTER_API_KEY with --base-url) not set in .env")

        base_url = config.get("base_url")
        client_kwargs = {"api_key": api_key, "timeout": 120}
        if base_url:
            client_kwargs["base_url"] = base_url
            client_kwargs["default_headers"] = {
                "HTTP-Referer": "https://github.com/opencursor",
                "X-Title": "opencursor-agent",
            }
        return OpenAI(**client_kwargs)

    def _call_api(self, client, system_prompt: str, user_text: str,
                  screenshot: Image.Image, config: dict,
                  on_reasoning: StreamCallback | None = None) -> ModelResponse:
        messages = self._build_openai_messages(system_prompt, user_text, screenshot)

        kwargs = {
            "model": self._get_model_id(config),
            "messages": messages,
            "max_tokens": config.get("max_tokens", 4096),
            "temperature": config.get("temperature", 0),
            "tools": TOOLS,
        }

        if on_reasoning is not None:
            kwargs["stream"] = True
            kwargs["stream_options"] = {"include_usage": True}

            raw_chunks: list[str] = []
            tool_call_chunks: dict[int, dict] = {}
            finish_reason = None
            usage = None
            reasoning_accumulated = ""

            for chunk in client.chat.completions.create(**kwargs):
                if not chunk.choices:
                    if chunk.usage:
                        usage = chunk.usage
                    continue

                delta = chunk.choices[0].delta

                # Text content = reasoning for tool-use models
                if delta.content:
                    raw_chunks.append(delta.content)
                    reasoning_accumulated += delta.content
                    on_reasoning(delta.content, reasoning_accumulated)

                # Accumulate tool call deltas
                if delta.tool_calls:
                    for tc_delta in delta.tool_calls:
                        idx = tc_delta.index
                        if idx not in tool_call_chunks:
                            tool_call_chunks[idx] = {"name": "", "arguments": ""}
                        if tc_delta.function:
                            if tc_delta.function.name:
                                tool_call_chunks[idx]["name"] = tc_delta.function.name
                            if tc_delta.function.arguments:
                                tool_call_chunks[idx]["arguments"] += tc_delta.function.arguments

                if chunk.choices[0].finish_reason:
                    finish_reason = chunk.choices[0].finish_reason

            raw = "".join(raw_chunks)

            if tool_call_chunks:
                tool_calls = [
                    {"name": tc["name"], "input": tc["arguments"]}
                    for _, tc in sorted(tool_call_chunks.items())
                ]
                self._print_debug(
                    finish_reason=finish_reason,
                    usage=vars(usage) if usage else None,
                    tool_calls=tool_calls,
                )
                parsed = parse_response_tool_use(tool_calls)
            else:
                raw = raw.strip()
                self._print_debug(
                    finish_reason=finish_reason,
                    usage=vars(usage) if usage else None,
                    raw=raw,
                )
                parsed = parse_response(raw)

            raw_str = raw or str(tool_call_chunks)
            return self._build_response(
                raw_str, parsed, self._openai_usage_dict(usage),
                reasoning=raw.strip() if tool_call_chunks and raw.strip() else None,
            )

        # Blocking path (--no-gui)
        resp = client.chat.completions.create(**kwargs)

        choice = resp.choices[0]
        raw = choice.message.content or ""

        if choice.message.tool_calls:
            tool_calls = [
                {"name": tc.function.name, "input": tc.function.arguments}
                for tc in choice.message.tool_calls
            ]
            self._print_debug(
                finish_reason=choice.finish_reason,
                usage=vars(resp.usage) if resp.usage else None,
                tool_calls=tool_calls,
            )
            parsed = parse_response_tool_use(tool_calls)
        else:
            raw = raw.strip()
            self._print_debug(
                finish_reason=choice.finish_reason,
                usage=vars(resp.usage) if resp.usage else None,
                raw=raw,
            )
            parsed = parse_response(raw)

        raw_str = raw or str(choice.message.tool_calls)
        return self._build_response(
            raw_str, parsed, self._openai_usage_dict(resp.usage),
            reasoning=raw.strip() if choice.message.tool_calls and raw.strip() else None,
        )

    def get_prompt_overrides(self) -> dict:
        return {
            "coordinate_instructions": "tool_use",
            "extra_rules": "- Use the provided tools to express your actions. Call exactly one tool per turn.\n",
        }
