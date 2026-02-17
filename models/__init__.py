"""Model adapter registry."""

from models.claude import ClaudeAdapter
from models.gemini import GeminiAdapter
from models.generic import GenericAdapter
from models.openai_gpt import OpenAIGPTAdapter
from models.qwen import QwenAdapter

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
