"""Claude adapter — Anthropic API (Sonnet 4.5) with tool_use for structured actions."""

import os
import sys

from PIL import Image

from adapters.base import ModelAdapter, ModelResponse
from parsing import parse_response, parse_response_tool_use
from screenshot import encode_image

TOOLS = [
    {
        "name": "click",
        "description": "Left-click on a UI element",
        "input_schema": {
            "type": "object",
            "properties": {
                "target": {"type": "string", "description": "Description of the element to click"},
                "x": {"type": "integer", "description": "X coordinate (0-1000 normalized, left=0 right=1000)"},
                "y": {"type": "integer", "description": "Y coordinate (0-1000 normalized, top=0 bottom=1000)"},
            },
            "required": ["target", "x", "y"],
        },
    },
    {
        "name": "double_click",
        "description": "Double-click on a UI element",
        "input_schema": {
            "type": "object",
            "properties": {
                "target": {"type": "string", "description": "Description of the element"},
                "x": {"type": "integer", "description": "X coordinate (0-1000)"},
                "y": {"type": "integer", "description": "Y coordinate (0-1000)"},
            },
            "required": ["target", "x", "y"],
        },
    },
    {
        "name": "right_click",
        "description": "Right-click on a UI element",
        "input_schema": {
            "type": "object",
            "properties": {
                "target": {"type": "string", "description": "Description of the element"},
                "x": {"type": "integer", "description": "X coordinate (0-1000)"},
                "y": {"type": "integer", "description": "Y coordinate (0-1000)"},
            },
            "required": ["target", "x", "y"],
        },
    },
    {
        "name": "type",
        "description": "Type text at the current cursor position",
        "input_schema": {
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "The text to type"},
            },
            "required": ["text"],
        },
    },
    {
        "name": "hotkey",
        "description": "Press a keyboard shortcut (e.g. ctrl+c, alt+f4, enter)",
        "input_schema": {
            "type": "object",
            "properties": {
                "keys": {"type": "string", "description": "Keys separated by + (e.g. ctrl+shift+s)"},
            },
            "required": ["keys"],
        },
    },
    {
        "name": "scroll",
        "description": "Scroll the mouse wheel",
        "input_schema": {
            "type": "object",
            "properties": {
                "direction": {"type": "string", "enum": ["up", "down", "left", "right"]},
                "amount": {"type": "integer", "description": "Number of scroll clicks (default 3)"},
            },
            "required": ["direction"],
        },
    },
    {
        "name": "drag",
        "description": "Drag from one point to another",
        "input_schema": {
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
    {
        "name": "wait",
        "description": "Pause before the next action",
        "input_schema": {
            "type": "object",
            "properties": {
                "seconds": {"type": "number", "description": "Seconds to wait (default 1)"},
            },
        },
    },
    {
        "name": "done",
        "description": "Signal that the goal has been accomplished",
        "input_schema": {
            "type": "object",
            "properties": {
                "reason": {"type": "string", "description": "Why the task is complete"},
            },
            "required": ["reason"],
        },
    },
]


class ClaudeAdapter(ModelAdapter):
    name = "claude"
    default_model_id = "claude-sonnet-4-5-20250929"

    def build_client(self, config: dict):
        try:
            import anthropic
        except ImportError:
            sys.exit("Claude adapter requires the anthropic package: pip install anthropic")

        api_key = os.getenv(config.get("api_key_env", "ANTHROPIC_API_KEY"))
        if not api_key:
            api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            sys.exit("ANTHROPIC_API_KEY not set in .env")
        return anthropic.Anthropic(api_key=api_key)

    def _call_api(self, client, system_prompt: str, user_text: str,
                  screenshot: Image.Image, config: dict) -> ModelResponse:
        b64 = encode_image(screenshot)

        resp = client.messages.create(
            model=self._get_model_id(config),
            max_tokens=config.get("max_tokens", 4096),
            system=system_prompt,
            tools=TOOLS,
            messages=[{
                "role": "user",
                "content": [
                    {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": b64}},
                    {"type": "text", "text": user_text},
                ],
            }],
        )

        usage = resp.usage
        raw_parts = []
        tool_calls = []

        for block in resp.content:
            if block.type == "text":
                raw_parts.append(block.text)
            elif block.type == "tool_use":
                tool_calls.append({"name": block.name, "input": block.input})

        raw = "\n".join(raw_parts)

        self._print_debug(
            finish_reason=resp.stop_reason,
            usage={"input_tokens": usage.input_tokens, "output_tokens": usage.output_tokens} if usage else None,
            raw=raw if raw else None,
            tool_calls=tool_calls if tool_calls else None,
        )

        if tool_calls:
            parsed = parse_response_tool_use(tool_calls)
        else:
            parsed = parse_response(raw)

        usage_dict = None
        if usage:
            usage_dict = {
                "prompt": usage.input_tokens,
                "completion": usage.output_tokens,
                "total": usage.input_tokens + usage.output_tokens,
            }

        return self._build_response(raw or str(tool_calls), parsed, usage_dict)

    def get_prompt_overrides(self) -> dict:
        return {
            "coordinate_instructions": "tool_use",
            "extra_rules": "- Use the provided tools to express your actions. Call exactly one tool per turn.\n",
        }
