"""GPT-4o adapter — OpenAI API with tool_use for structured actions."""

import os
import sys

from PIL import Image

from models.base import ModelAdapter, ModelResponse
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
        kwargs = {"api_key": api_key, "timeout": 120}
        if base_url:
            kwargs["base_url"] = base_url
            kwargs["default_headers"] = {
                "HTTP-Referer": "https://github.com/opencursor",
                "X-Title": "opencursor-agent",
            }
        return OpenAI(**kwargs)

    def _call_api(self, client, system_prompt: str, user_text: str,
                  screenshot: Image.Image, config: dict) -> ModelResponse:
        messages = self._build_openai_messages(system_prompt, user_text, screenshot)

        resp = client.chat.completions.create(
            model=self._get_model_id(config),
            messages=messages,
            max_tokens=config.get("max_tokens", 4096),
            temperature=config.get("temperature", 0),
            tools=TOOLS,
        )

        choice = resp.choices[0]
        raw = choice.message.content or ""

        # Parse tool calls or fall back to XML
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

        return self._build_response(
            raw or str(choice.message.tool_calls),
            parsed,
            self._openai_usage_dict(resp.usage),
        )

    def get_prompt_overrides(self) -> dict:
        return {
            "coordinate_instructions": "tool_use",
            "extra_rules": "- Use the provided tools to express your actions. Call exactly one tool per turn.\n",
        }
