# Chat Provider Configuration

The legal chat assistant uses an explicit provider selector. **Gemini is the
default**; OpenCode Go remains available as an opt-in backup. The app never
falls back automatically, so a Gemini quota or service error cannot silently
send traffic to another provider.

## Default: Gemini

Install dependencies and configure Streamlit secrets:

```toml
CHAT_PROVIDER = "gemini"
GEMINI_API_KEY = "..."
```

The adapter in `utils/gemini_chat.py` uses the stable
`gemini-2.5-flash` model through Google's native REST API. Streaming uses the
API's SSE endpoint and the project's existing `requests` dependency, avoiding
another SDK and its startup/install overhead. Retrieval and follow-up
suggestions remain local.

To enforce a zero-dollar ceiling, do not attach billing to the Google AI Studio
project. Requests stop at the free-tier quota instead of becoming paid usage.
Free-tier prompts may be used by Google to improve its products, so users should
not submit confidential or privileged information.

## Retained backup: OpenCode Go

The original adapter remains in `utils/opencode_chat.py`, and the `openai`
dependency remains in `requirements.txt`. To select it deliberately:

```toml
CHAT_PROVIDER = "opencode"
OPENCODE_API_KEY = "..."
```

## Retained backup: OpenRouter

The OpenRouter adapter in `utils/openrouter_chat.py` provides access to any
model available through OpenRouter's OpenAI-compatible API. To use it:

```toml
CHAT_PROVIDER = "openrouter"
OPENROUTER_API_KEY = "sk-or-v1-..."

# Optional: override the default model (google/gemini-2.5-flash)
OPENROUTER_MODEL = "anthropic/claude-3.5-haiku"
```

The adapter sends `HTTP-Referer` and `X-Title` headers for OpenRouter ranking.

Restart Streamlit after changing providers. Switching providers does not alter
retrieval, source cards, navigation, conversation state, or response formatting.

## Relevant code

- `utils/chat_provider.py` — explicit provider router
- `utils/gemini_chat.py` — native Gemini adapter
- `utils/opencode_chat.py` — retained OpenCode Go adapter
- `utils/openrouter_chat.py` — OpenRouter adapter (any model via OpenAI-compatible API)
- `cases.py` — home-page Ask & Browse UI, retrieval orchestration, and streaming UI

## Changing the Gemini model

Update `MODEL` in `utils/gemini_chat.py`. Prefer stable model identifiers over
preview or `latest` aliases so behavior does not change unexpectedly.
