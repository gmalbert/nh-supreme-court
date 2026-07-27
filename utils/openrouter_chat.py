"""OpenRouter API client for legal chat assistant.

Supports any model available through OpenRouter via the OpenAI-compatible API.
"""

from __future__ import annotations

import os
from typing import List, Dict, Optional, Generator

import streamlit as st
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env"))

try:
    from openai import OpenAI

    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False


class OpenRouterClient:
    """Wrapper for OpenRouter API using OpenAI-compatible client."""

    def __init__(self, api_key: Optional[str] = None):
        if not OPENAI_AVAILABLE:
            raise ImportError("openai library not installed. Run: pip install openai")

        self.api_key = api_key or self._get_api_key()

        if not self.api_key:
            raise ValueError(
                "OpenRouter API key not found. Set OPENROUTER_API_KEY in "
                ".streamlit/secrets.toml or environment variable."
            )

        self.client = OpenAI(
            api_key=self.api_key,
            base_url="https://openrouter.ai/api/v1",
            default_headers={
                "HTTP-Referer": "https://github.com/anomalyco/nh-supreme-court",
                "X-Title": "Granite State Appeals",
            },
        )

        self.model = os.environ.get("OPENROUTER_MODEL", "google/gemini-2.5-flash")
        self.max_tokens = 2000
        self.temperature = 0.2

    def _get_api_key(self) -> Optional[str]:
        if os.environ.get("OPENROUTER_API_KEY"):
            return os.environ.get("OPENROUTER_API_KEY")

        try:
            return st.secrets.get("OPENROUTER_API_KEY")
        except Exception:
            return None

    def generate_response(
        self,
        user_message: str,
        case_context: str,
        conversation_history: Optional[List[Dict[str, str]]] = None,
        stream: bool = False,
    ) -> str | Generator[str, None, None]:
        system_prompt = self._build_system_prompt()

        messages = [{"role": "system", "content": system_prompt}]

        if conversation_history:
            messages.extend(conversation_history[-10:])

        context_message = f"""Relevant New Hampshire Supreme Court cases:

{case_context}

Answer the question directly from these cases. Cite specific case names."""

        messages.append({"role": "user", "content": context_message})
        messages.append({"role": "user", "content": user_message})

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                max_tokens=self.max_tokens,
                temperature=self.temperature,
                stream=stream,
            )

            if isinstance(response, str):
                return f"⚠️ API returned string instead of completion object: {response[:200]}"

            if stream:
                return self._stream_response(response)

            if not hasattr(response, "choices") or not response.choices:
                return "⚠️ API returned empty response."
            return response.choices[0].message.content

        except Exception as e:
            error_msg = f"OpenRouter API error: {str(e)}"
            if "authentication" in str(e).lower() or "api key" in str(e).lower():
                error_msg = "API authentication failed. Please check your OpenRouter API key."
            elif "rate limit" in str(e).lower():
                error_msg = "Rate limit exceeded. Please try again in a moment."
            elif "model" in str(e).lower():
                error_msg = (
                    f"Model error. The model '{self.model}' may not be available "
                    "via OpenRouter. Try a different model by setting OPENROUTER_MODEL."
                )

            return f"⚠️ {error_msg}"

    def _stream_response(self, response) -> Generator[str, None, None]:
        for chunk in response:
            if chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content

    def _build_system_prompt(self) -> str:
        return """You are a legal research assistant for New Hampshire Supreme Court cases.

Always answer the question. Cite cases by exact name in italics, e.g. *State v. Smith*.
Never comment on what is or is not in the case list — just answer using the cases you have.
If asked about a specific case, check whether it appears below; if yes, summarize it;
if it does not appear, politely say that case wasn't among the search results and offer
to look for similar cases instead. Do not invent a case, holding, quotation, or procedural fact.
When asked who wrote an opinion, identify the author(s) from the case record.
Provide legal information, not legal advice."""

    def extract_follow_up_questions(
        self, user_message: str, assistant_response: str
    ) -> List[str]:
        prompt = f"""Based on this conversation, suggest 3 concise follow-up questions the user might want to ask. Each question should be 8-15 words.

User asked: {user_message}

Assistant responded: {assistant_response[:500]}...

Return ONLY 3 questions, one per line, no numbering or bullets."""

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=150,
                temperature=0.8,
            )

            questions_text = response.choices[0].message.content
            questions = [q.strip() for q in questions_text.split("\n") if q.strip()]

            return questions[:3] if len(questions) >= 3 else questions

        except Exception:
            return [
                "What were the key facts in these cases?",
                "How do these cases compare?",
                "Are there related cases I should know about?",
            ]


_client: OpenRouterClient | None = None


def get_client() -> OpenRouterClient:
    global _client
    if _client is None:
        _client = OpenRouterClient()
    return _client


def generate_chat_response(
    user_message: str,
    case_context: str,
    conversation_history: Optional[List[Dict[str, str]]] = None,
    stream: bool = False,
) -> str | Generator[str, None, None]:
    client = get_client()
    return client.generate_response(user_message, case_context, conversation_history, stream)


def extract_follow_ups(user_message: str, assistant_response: str) -> List[str]:
    client = get_client()
    return client.extract_follow_up_questions(user_message, assistant_response)
