"""Native Gemini provider for the legal chat assistant."""

from __future__ import annotations

import os
import json
from typing import Generator, Optional

import requests
import streamlit as st
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env"))


MODEL = "gemini-2.5-flash"
MAX_OUTPUT_TOKENS = 1500
TEMPERATURE = 0.2


def _api_key() -> Optional[str]:
    key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if key:
        return key
    try:
        return st.secrets.get("GEMINI_API_KEY") or st.secrets.get("GOOGLE_API_KEY")
    except Exception:
        return None


def _system_prompt() -> str:
    return """You are a legal research assistant for New Hampshire Supreme Court cases.

Always answer the question. Cite cases by exact name in italics, e.g. *State v. Smith*.
Never comment on what is or is not in the case list — just answer using the cases you have.
If asked about a specific case, check whether it appears below; if yes, summarize it;
if it does not appear, politely say that case wasn't among the search results and offer
to look for similar cases instead. Do not invent a case, holding, quotation, or procedural fact.
When asked who wrote an opinion, identify the author(s) from the case record.
Provide legal information, not legal advice."""


def _prompt(user_message: str, case_context: str, conversation_history: list[dict] | None) -> str:
    history_lines = []
    for message in (conversation_history or [])[-10:]:
        role = "User" if message.get("role") == "user" else "Assistant"
        history_lines.append(f"{role}: {message.get('content', '')}")
    history = "\n\n".join(history_lines) or "No prior conversation."
    return f"""Prior conversation:
{history}

Relevant New Hampshire Supreme Court cases:
{case_context}

Current question:
{user_message}

Answer the question directly from the cases above. Cite the relevant case names."""


class GeminiClient:
    """Small adapter exposing the same interface as the retained OpenCode client."""

    def __init__(self, api_key: str | None = None):
        key = api_key or _api_key()
        if not key:
            raise ValueError(
                "Gemini API key not found. Set GEMINI_API_KEY in "
                ".streamlit/secrets.toml or the environment."
            )
        self.api_key = key
        self.model = MODEL

    def _payload(self, prompt: str) -> dict:
        return {
            "system_instruction": {"parts": [{"text": _system_prompt()}]},
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": TEMPERATURE,
                "maxOutputTokens": MAX_OUTPUT_TOKENS,
            },
        }

    @staticmethod
    def _text_from_response(data: dict) -> str:
        chunks = []
        for candidate in data.get("candidates", []):
            for part in (candidate.get("content") or {}).get("parts", []):
                if part.get("text"):
                    chunks.append(part["text"])
        return "".join(chunks)

    def generate_response(
        self,
        user_message: str,
        case_context: str,
        conversation_history: list[dict] | None = None,
        stream: bool = False,
    ) -> str | Generator[str, None, None]:
        prompt = _prompt(user_message, case_context, conversation_history)
        payload = self._payload(prompt)

        if stream:
            return self._stream(payload)

        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent"
        response = requests.post(
            url,
            headers={"x-goog-api-key": self.api_key, "Content-Type": "application/json"},
            json=payload,
            timeout=90,
        )
        response.raise_for_status()
        return self._text_from_response(response.json())

    def _stream(self, payload: dict) -> Generator[str, None, None]:
        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}"
            ":streamGenerateContent?alt=sse"
        )
        with requests.post(
            url,
            headers={"x-goog-api-key": self.api_key, "Content-Type": "application/json"},
            json=payload,
            stream=True,
            timeout=90,
        ) as response:
            response.raise_for_status()
            for line in response.iter_lines(decode_unicode=True):
                if not line or not line.startswith("data:"):
                    continue
                data = json.loads(line[5:].strip())
                text = self._text_from_response(data)
                if text:
                    yield text


_client: GeminiClient | None = None


def get_client() -> GeminiClient:
    global _client
    if _client is None:
        _client = GeminiClient()
    return _client


def generate_chat_response(
    user_message: str,
    case_context: str,
    conversation_history: list[dict] | None = None,
    stream: bool = False,
):
    return get_client().generate_response(user_message, case_context, conversation_history, stream)
