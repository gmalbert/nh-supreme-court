"""Provider selector for legal chat.

Gemini is deliberately the default. OpenCode is retained as an opt-in backup and
is never selected automatically after an error, preventing surprise usage costs.
"""

from __future__ import annotations

import os

from dotenv import load_dotenv
from utils.runtime_cache import streamlit_secret

load_dotenv(os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env"))


SUPPORTED_PROVIDERS = {"gemini", "opencode", "openrouter"}


def provider_name() -> str:
    configured = os.environ.get("CHAT_PROVIDER")
    if not configured:
        configured = streamlit_secret("CHAT_PROVIDER")
    name = (configured or "gemini").strip().lower()
    if name not in SUPPORTED_PROVIDERS:
        raise ValueError(f"Unsupported CHAT_PROVIDER '{name}'. Use: gemini, opencode, or openrouter.")
    return name


def generate_chat_response(*args, **kwargs):
    """Lazy-load and call only the explicitly configured provider."""
    name = provider_name()
    if name == "gemini":
        from utils.gemini_chat import generate_chat_response as generate
    elif name == "opencode":
        from utils.opencode_chat import generate_chat_response as generate
    else:
        from utils.openrouter_chat import generate_chat_response as generate
    return generate(*args, **kwargs)
