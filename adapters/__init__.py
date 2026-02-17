"""Model adapter registry."""

from adapters.claude import ClaudeAdapter
from adapters.gemini import GeminiAdapter
from adapters.generic import GenericAdapter
from adapters.openai_gpt import OpenAIGPTAdapter
from adapters.qwen import QwenAdapter

MODEL_REGISTRY = {
    "qwen": QwenAdapter,
    "gpt4o": OpenAIGPTAdapter,
    "claude": ClaudeAdapter,
    "gemini": GeminiAdapter,
    "generic": GenericAdapter,
}


def get_adapter(name: str):
    cls = MODEL_REGISTRY.get(name)
    if not cls:
        available = ", ".join(MODEL_REGISTRY.keys())
        raise ValueError(f"Unknown model adapter '{name}'. Available: {available}")
    return cls()
