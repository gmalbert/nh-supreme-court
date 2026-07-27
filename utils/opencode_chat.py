"""
OpenCode.ai API client for legal chatbox.
Supports DeepSeek Flash model via OpenAI-compatible API.
"""

import os
import json
from typing import List, Dict, Optional, Generator
import streamlit as st

from dotenv import load_dotenv
load_dotenv()

try:
    from openai import OpenAI
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False


class OpenCodeClient:
    """
    Wrapper for OpenCode.ai API using OpenAI-compatible client.
    """

    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize OpenCode.ai client.

        Args:
            api_key: OpenCode.ai API key. If None, tries st.secrets then env var.
        """
        if not OPENAI_AVAILABLE:
            raise ImportError(
                "openai library not installed. Run: pip install openai"
            )

        # Try multiple sources for API key
        self.api_key = api_key or self._get_api_key()

        if not self.api_key:
            raise ValueError(
                "OpenCode.ai API key not found. Set OPENCODE_API_KEY in "
                ".streamlit/secrets.toml or environment variable."
            )

        # Initialize OpenAI client with OpenCode.ai base URL
        self.client = OpenAI(
            api_key=self.api_key,
            base_url="https://opencode.ai/zen/go/v1"
        )

        self.model = "deepseek-v4-flash"
        self.max_tokens = 2000
        self.temperature = 0.7

    def _get_api_key(self) -> Optional[str]:
        """Get API key from environment, then secrets."""
        # Try environment variable first (for local .env loading)
        if os.environ.get("OPENCODE_API_KEY"):
            return os.environ.get("OPENCODE_API_KEY")

        # Then try Streamlit secrets
        if hasattr(st, "secrets") and "OPENCODE_API_KEY" in st.secrets:
            return st.secrets["OPENCODE_API_KEY"]

        return None

    def generate_response(
        self,
        user_message: str,
        case_context: str,
        conversation_history: Optional[List[Dict[str, str]]] = None,
        stream: bool = False
    ) -> str | Generator[str, None, None]:
        """
        Generate a response from the LLM.

        Args:
            user_message: The user's current question
            case_context: Retrieved case information formatted as text
            conversation_history: Previous messages [{"role": "user/assistant", "content": "..."}]
            stream: If True, return a generator for streaming responses

        Returns:
            Response text or generator yielding text chunks
        """
        system_prompt = self._build_system_prompt()

        messages = [{"role": "system", "content": system_prompt}]

        # Add conversation history (last 5 exchanges max)
        if conversation_history:
            messages.extend(conversation_history[-10:])  # 5 pairs of user/assistant

        # Add current context and user message
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
                stream=stream
            )

            # Debug: Check what type of response we got
            if isinstance(response, str):
                return f"⚠️ API returned string instead of completion object: {response[:200]}"

            if stream:
                return self._stream_response(response)

            if not hasattr(response, "choices") or not response.choices:
                return "⚠️ API returned empty response."
            return response.choices[0].message.content

        except Exception as e:
            error_msg = f"OpenCode.ai API error: {str(e)}"
            if "authentication" in str(e).lower() or "api key" in str(e).lower():
                error_msg = "API authentication failed. Please check your OpenCode.ai API key."
            elif "rate limit" in str(e).lower():
                error_msg = "Rate limit exceeded. Please try again in a moment."
            elif "model" in str(e).lower():
                error_msg = f"Model error. The model '{self.model}' may not be available. Try a different model."

            return f"⚠️ {error_msg}"

    def _stream_response(self, response) -> Generator[str, None, None]:
        """Stream response chunks."""
        for chunk in response:
            if chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content

    def _build_system_prompt(self) -> str:
        """Build the system prompt for the LLM."""
        return """You are a legal research assistant for New Hampshire Supreme Court cases.

Always answer the question. Cite cases by exact name in italics, e.g. *State v. Smith*.
Never comment on what is or is not in the case list — just answer using the cases you have.
If asked about a specific case, check whether it appears below; if yes, summarize it;
if it does not appear, politely say that case wasn't among the search results and offer
to look for similar cases instead. Do not invent a case, holding, quotation, or procedural fact.
When asked who wrote an opinion, identify the author(s) from the case record.
Provide legal information, not legal advice."""

    def extract_follow_up_questions(
        self,
        user_message: str,
        assistant_response: str
    ) -> List[str]:
        """
        Generate 3 follow-up questions based on the conversation.

        Args:
            user_message: The user's question
            assistant_response: The assistant's response

        Returns:
            List of 3 follow-up question strings
        """
        prompt = f"""Based on this conversation, suggest 3 concise follow-up questions the user might want to ask. Each question should be 8-15 words.

User asked: {user_message}

Assistant responded: {assistant_response[:500]}...

Return ONLY 3 questions, one per line, no numbering or bullets."""

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=150,
                temperature=0.8
            )

            questions_text = response.choices[0].message.content
            questions = [q.strip() for q in questions_text.split('\n') if q.strip()]

            # Return exactly 3 questions
            return questions[:3] if len(questions) >= 3 else questions

        except Exception:
            # Fallback generic questions if API fails
            return [
                "What were the key facts in these cases?",
                "How do these cases compare?",
                "Are there related cases I should know about?"
            ]


# Singleton instance
_client = None

def get_client() -> OpenCodeClient:
    """Get or create singleton OpenCode.ai client."""
    global _client
    if _client is None:
        _client = OpenCodeClient()
    return _client


# Convenience functions for direct use
def generate_chat_response(
    user_message: str,
    case_context: str,
    conversation_history: Optional[List[Dict[str, str]]] = None,
    stream: bool = False
) -> str | Generator[str, None, None]:
    """Generate a chat response. See OpenCodeClient.generate_response for details."""
    client = get_client()
    return client.generate_response(user_message, case_context, conversation_history, stream)


def extract_follow_ups(user_message: str, assistant_response: str) -> List[str]:
    """Extract follow-up questions. See OpenCodeClient.extract_follow_up_questions."""
    client = get_client()
    return client.extract_follow_up_questions(user_message, assistant_response)
