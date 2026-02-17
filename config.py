"""Configuration loading: defaults -> .env -> CLI args."""

import os

from dotenv import load_dotenv

load_dotenv()

DEFAULTS = {
    "model": "qwen",
    "model_id": None,
    "base_url": None,
    "api_key_env": "OPENROUTER_API_KEY",
    "temperature": 0,
    "max_tokens": 4096,
    "max_steps": 30,
    "step_delay": 1.5,
    "debug": False,
    "no_gui": False,
}


def load_config(cli_args: dict | None = None) -> dict:
    """Merge defaults, env vars, and CLI args into a config dict."""
    config = {**DEFAULTS}

    # Env overrides
    if os.getenv("OPENCURSOR_MODEL"):
        config["model"] = os.getenv("OPENCURSOR_MODEL")
    if os.getenv("OPENCURSOR_MODEL_ID"):
        config["model_id"] = os.getenv("OPENCURSOR_MODEL_ID")
    if os.getenv("OPENCURSOR_BASE_URL"):
        config["base_url"] = os.getenv("OPENCURSOR_BASE_URL")
    if os.getenv("OPENCURSOR_API_KEY_ENV"):
        config["api_key_env"] = os.getenv("OPENCURSOR_API_KEY_ENV")

    # CLI overrides (only non-None values)
    if cli_args:
        for k, v in cli_args.items():
            if v is not None:
                config[k] = v

    return config
