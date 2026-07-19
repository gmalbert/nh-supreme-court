# Legal Chat Implementation — Complete Handoff

**Source repo:** `supreme-court` (U.S. Supreme Court)
**Target repo:** `nh-supreme-court` (NH Supreme Court)
**Purpose:** Replicate the full legal chat assistant in a new repository.

---

## Table of Contents

1. [Architecture Overview](#1-architecture-overview)
2. [File Map](#2-file-map)
3. [Data Pipeline](#3-data-pipeline)
4. [Core Modules](#4-core-modules)
   - [4A. Chat Page (`pages/14_Chat.py`)](#4a-chat-page)
   - [4B. Chat Retriever (`utils/chat_retriever.py`)](#4b-chat-retriever)
   - [4C. Chat Formatter (`utils/chat_formatter.py`)](#4c-chat-formatter)
   - [4D. Chat Provider (`utils/chat_provider.py`)](#4d-chat-provider)
   - [4E. Gemini Provider (`utils/gemini_chat.py`)](#4e-gemini-provider)
   - [4F. OpenCode Backup (`utils/opencode_chat.py`)](#4f-opencode-backup)
5. [Hybrid Retrieval Package (`utils/retrieval/`)](#5-hybrid-retrieval-package)
   - [5A. Data Models](#5a-models)
   - [5B. Query Analyzer](#5b-query-analyzer)
   - [5C. Exact Case Index](#5c-exact-index)
   - [5D. Lexical (TF-IDF) Index](#5d-lexical-index)
   - [5E. Dense (Embedding) Index](#5e-dense-index)
   - [5F. Rank Fusion](#5f-rank-fusion)
   - [5G. Metadata Hydration](#5g-metadata-hydration)
   - [5H. Context Builder](#5h-context-builder)
   - [5I. Sufficiency Evaluator](#5i-sufficiency-evaluator)
   - [5J. Transcript Index](#5j-transcript-index)
   - [5K. Diagnostics](#5k-diagnostics)
   - [5L. Normalization Utilities](#5l-normalization)
   - [5M. Legacy Adapter](#5m-legacy-adapter)
   - [5N. Service Facade](#5n-service-facade)
6. [Referential Follow-Up Detection](#6-referential-follow-up-detection)
7. [Conversation-Aware Retrieval](#7-conversation-aware-retrieval)
8. [Case Merging & Deduplication](#8-case-merging--deduplication)
9. [Follow-Up Suggestions](#9-follow-up-suggestions)
10. [Tests](#10-tests)
11. [Dependencies](#11-dependencies)
12. [Environment Configuration](#12-environment-configuration)

---

## 1. Architecture Overview

```
User types question
       │
       ▼
pages/14_Chat.py
  ├── is_referential_followup() — detect follow-ups
  ├── build_retrieval_query() — expand if referential
  ├── retrieve_cases() — search corpus
  │     ├── Hybrid RetrievalService (preferred)
  │     │     ├── query_analyzer → detect intents
  │     │     ├── exact_index → case name/citation/docket match
  │     │     ├── lexical_index → TF-IDF search
  │     │     ├── dense_index → embedding search (optional)
  │     │     ├── fusion → RRF rank merge
  │     │     ├── metadata → hydrate CaseEvidence objects
  │     │     └── sufficiency → check if evidence answers query
  │     └── Legacy TF-IDF (fallback)
  │           └── utils/text_search.py
  ├── merge_retrieved_cases() — deduplicate with prior cases
  ├── format_context() — build LLM prompt block
  ├── generate_chat_response() → LLM call
  │     ├── gemini_chat.py (default) or
  │     └── opencode_chat.py (opt-in backup)
  ├── format_with_links() — italics → markdown links
  ├── render_sources() — case cards with View buttons
  └── render_follow_ups() — case-specific follow-up buttons
```

---

## 2. File Map

| File | Role | Portable? |
|---|---|---|
| `pages/14_Chat.py` | Main chat UI page | **Rewrite** (adapt to target Streamlit structure) |
| `utils/chat_retriever.py` | TF-IDF retrieval, referential detection, query building, case merging | **Mostly copy** (change data paths, source labels) |
| `utils/chat_formatter.py` | Format LLM responses with case links, source cards, follow-up buttons | **Mostly copy** |
| `utils/chat_provider.py` | Provider selector (gemini vs opencode) | **Copy verbatim** |
| `utils/gemini_chat.py` | Gemini REST/SSE adapter (default provider) | **Copy verbatim** |
| `utils/opencode_chat.py` | OpenCode.ai adapter (backup provider) | **Copy verbatim** |
| `utils/text_search.py` | Legacy TF-IDF search index | **Rewrite** (point to NH case data) |
| `utils/retrieval/` | Hybrid retrieval package | **Copy verbatim** (data-format-agnostic) |
| `utils/retrieval/__init__.py` | Package exports | Copy verbatim |
| `utils/retrieval/models.py` | Data contracts (Intent, QueryPlan, etc.) | Copy verbatim |
| `utils/retrieval/query_analyzer.py` | Intent detection from query text | **Adapt** (NH-specific intents) |
| `utils/retrieval/exact_index.py` | Exact case-name, citation, docket resolution | **Copy verbatim** |
| `utils/retrieval/lexical_index.py` | TF-IDF case + transcript search | **Copy verbatim** |
| `utils/retrieval/dense_index.py` | Optional embedding-based search | Copy verbatim |
| `utils/retrieval/fusion.py` | Reciprocal rank fusion | Copy verbatim |
| `utils/retrieval/metadata.py` | Hydrate CaseEvidence from raw data | **Rewrite** (NH data format) |
| `utils/retrieval/context_builder.py` | Intent-aware LLM prompt assembly | **Copy verbatim** |
| `utils/retrieval/sufficiency.py` | Evidence sufficiency checks | **Copy verbatim** |
| `utils/retrieval/transcript_index.py` | Oral argument transcript search | **Skip** (unless NH has transcripts) |
| `utils/retrieval/diagnostics.py` | Latency tracking, debug rendering | Copy verbatim |
| `utils/retrieval/normalize.py` | HTML/text/case-name cleaning | Copy verbatim |
| `utils/retrieval/legacy_adapter.py` | CaseEvidence → legacy dict | **Copy verbatim** |
| `utils/retrieval/service.py` | RetrievalService facade | **Adapt** (data paths, column names) |
| `tests/test_chat_conversation.py` | Unit tests for retrieval logic | **Copy verbatim** (imports from chat_retriever) |
| `tests/test_chat_navigation.py` | URL navigation, formatting tests | **Adapt** (NH case page URLs) |
| `tests/test_chat_providers.py` | Provider selection tests | **Copy verbatim** |
| `tests/test_chat_setup.py` | Integration smoke tests | **Rewrite** (NH data paths) |

---

## 3. Data Pipeline

The chat retriever needs a case corpus with the following columns (adjust names for NH data):

```python
# Required columns for utils/text_search.py
columns=[
    "name",           # Case name, e.g. "Riley v. California"
    "term",           # Supreme Court term year, e.g. "2013"
    "href",           # Unique case URL/ID
    "docket_number",  # e.g. "11-1425"
    "facts_of_the_case",  # Narrative facts
    "question",       # Legal question presented
    "description",    # Optional short summary
    "conclusion",     # Holding/outcome (critical for LLM context)
    "decisions",      # JSON: votes, opinion_type per justice
]
```

**NH Supreme Court adaptation:** Map your NH fields:

| Source field | NH field mapping | Used in |
|---|---|---|
| `name` | `case_name` | Chat retriever, display |
| `term` | `term_year` | Metadata |
| `href` | `case_number` (or URL) | Deduplication key |
| `docket_number` | `case_number` | Display |
| `facts_of_the_case` | `facts` or `plain_text_summary` | LLM context |
| `question` | `question_presented` or `issue` | LLM context |
| `conclusion` | `outcome` or `ruling` | LLM context (labeled as Holding) |
| `description` | `summary` or `headnote` | LLM context |
| `decisions` | vote JSON or structured fields | Vote split, opinion authors |

### Data Build Script

For NH, you'll want a script like `scripts/build_nh_case_detail.py`:

```python
"""Build the case_detail.parquet used by the chat retriever."""
import pandas as pd
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
INPUT_CSV = REPO_ROOT / "data" / "processed" / "opinions.csv"
OUTPUT_PARQUET = REPO_ROOT / "data" / "case_detail.parquet"

df = pd.read_csv(INPUT_CSV)

# Map NH columns to the expected schema
detail = pd.DataFrame({
    "name": df["case_name"],
    "term": df["term_year"],
    "href": df["case_number"],  # or build URL
    "docket_number": df["case_number"],
    "facts_of_the_case": df["plain_text_summary"],  # or facts column
    "question": df.get("question_presented", ""),
    "conclusion": df.get("outcome", ""),
    "description": df.get("summary", ""),
    "decisions": df.get("votes_json", ""),  # optional
    "citation": df.get("citation", ""),
    "majority_author": df.get("author", ""),
})

detail.to_parquet(OUTPUT_PARQUET, index=False)
```

### For the hybrid retrieval artifacts (optional upgrade):

```python
# scripts/build_retrieval_artifacts.py
import pandas as pd
import numpy as np
import json
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
OUT_DIR = REPO_ROOT / "data" / "retrieval"
OUT_DIR.mkdir(parents=True, exist_ok=True)

# 1. Build case_documents.parquet with a combined retrieval_text column
df = pd.read_parquet(REPO_ROOT / "data" / "case_detail.parquet")

# Combine text fields into one column for TF-IDF search
def combine(row):
    parts = [
        row.get("name"),
        row.get("facts_of_the_case"),
        row.get("question"),
        row.get("conclusion"),
        row.get("description"),
    ]
    return " ".join(str(p) for p in parts if p and str(p) not in ("nan", "None"))

df["retrieval_text"] = df.apply(combine, axis=1)
df["case_id"] = df["href"]  # or generate stable case_id

# Ensure all required columns for MetadataHydrator
required_cols = [
    "case_id", "name", "href", "term", "docket_number", "citation",
    "facts_of_the_case", "question", "conclusion", "description",
    "retrieval_text", "majority_author",
]
for col in required_cols:
    if col not in df.columns:
        df[col] = ""

documents = df[required_cols + ["decisions"] if "decisions" in df.columns else required_cols]
documents.to_parquet(OUT_DIR / "case_documents.parquet", index=False)

# 2. Build TF-IDF index (optional — built at runtime by LexicalCaseIndex)
#    Not needed for runtime; LexicalCaseIndex builds it on load.

# 3. Build dense embeddings (optional)
# python -c "
# from sentence_transformers import SentenceTransformer
# import pandas as pd, numpy as np
# df = pd.read_parquet('data/retrieval/case_documents.parquet')
# model = SentenceTransformer('BAAI/bge-small-en-v1.5')
# texts = [row.get('retrieval_text') or row.get('name') for _, row in df.iterrows()]
# emb = model.encode(texts, normalize_embeddings=True, show_progress_bar=True)
# np.save('data/retrieval/case_embeddings.npy', emb)
# json.dump({'model': 'BAAI/bge-small-en-v1.5', 'count': len(emb)},
#           open('data/retrieval/case_embedding_meta.json', 'w'))
# "
```

---

## 4. Core Modules

### 4A. Chat Page

**File:** `pages/14_Chat.py`

Key things to adapt for NH:

1. **Source options** — change from `{"🏛️ U.S. Supreme Court": "supreme-court"}` to `{"⚖️ NH Supreme Court": "nh-supreme-court"}`
2. **URL generation** — change `/Cases?...` to your NH case page route
3. **Example questions** — replace with NH-specific examples
4. **Year range in disclaimer** — find earliest/latest year in your NH dataset

Full code below. Mark sections that need NH adaptation with comments.

```python
"""
Legal Chat Assistant - Interactive Q&A with case citations
"""

import sys
import os
import importlib.util
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import streamlit as st
from dotenv import load_dotenv
from datetime import datetime
from typing import List, Dict

# Load environment before any provider imports
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env"))

from utils.chat_formatter import format_with_links, normalize_case_links, render_sources, render_follow_ups


def _hybrid_retrieval_available() -> bool:
    """Return True if the durable hybrid retrieval artifacts exist."""
    try:
        from pathlib import Path
        repo_root = Path(__file__).resolve().parent.parent
        return (repo_root / "data" / "retrieval" / "case_documents.parquet").exists()
    except Exception:
        return False


def _retrieve_via_hybrid(
    query: str,
    previous_cases: List[str],
    num_cases: int,
) -> tuple[List[Dict], Dict]:
    """Use the hybrid RetrievalService and emit legacy-shaped case dicts."""
    try:
        from utils.retrieval import (
            build_context as _build_context,
            evidence_to_legacy,
        )
        from utils.retrieval.service import _try_load_service
    except Exception:
        return [], {}

    try:
        service = _try_load_service()
    except Exception:
        return [], {}
    if not service.is_ready():
        return [], {}

    try:
        response = service.retrieve(query, previous_cases=tuple(previous_cases or ()), limit=num_cases)
    except Exception:
        return [], {}
    cases = [evidence_to_legacy(case) for case in response.cases]
    diagnostics = {
        "plan": response.plan,
        "missing_fields": list(response.missing_fields),
        "sufficient": response.sufficient,
        "context": _build_context(response),
        "fused_trace": response.diagnostics.get("trace", {}),
        "latency": response.diagnostics.get("latency", {}),
    }
    return cases, diagnostics


# ══════════════════════════════════════════════════════════════════════════════
# PAGE CONFIGURATION
# ══════════════════════════════════════════════════════════════════════════════

# ADAPT: Change title for NH
st.title("💬 Legal Chat Assistant")
st.caption("Ask questions about legal cases in natural language")

st.markdown("""
<style>
    .stChatInputContainer textarea {
        min-height: 80px !important;
        height: 80px !important;
    }
</style>
""", unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════════════════════
# SESSION STATE
# ══════════════════════════════════════════════════════════════════════════════

if "chat_messages" not in st.session_state:
    st.session_state.chat_messages = []
if "chat_query_count" not in st.session_state:
    st.session_state.chat_query_count = 0
if "chat_source" not in st.session_state:
    # ADAPT: Change default source
    st.session_state.chat_source = "nh-supreme-court"


# ══════════════════════════════════════════════════════════════════════════════
# CHAT CONTROLS
# ══════════════════════════════════════════════════════════════════════════════

query_limit = 20
# ADAPT: Change source label and key
source_options = {"⚖️ NH Supreme Court": "nh-supreme-court"}
selected_source_label = list(source_options.keys())[0]
st.session_state.chat_source = source_options[selected_source_label]


# ══════════════════════════════════════════════════════════════════════════════
# SIDEBAR
# ══════════════════════════════════════════════════════════════════════════════

with st.sidebar:
    st.header("⚙️ Chat Actions")
    if st.button("🗑️ Clear Chat", type="secondary", use_container_width=True):
        st.session_state.chat_messages = []
        st.session_state.chat_query_count = 0
        st.rerun()

    if st.session_state.chat_messages:
        if st.button("📥 Export Chat", use_container_width=True):
            st.session_state.show_export = True

    with st.expander("🔑 API Configuration", expanded=False):
        _provider = (os.environ.get("CHAT_PROVIDER") or "gemini").strip().lower()
        try:
            _provider = (st.secrets.get("CHAT_PROVIDER") or _provider).strip().lower()
        except Exception:
            pass

        _key_name = "GEMINI_API_KEY" if _provider == "gemini" else "OPENCODE_API_KEY"
        _package_name = "requests" if _provider == "gemini" else "openai"
        st.caption(f"Active provider: **{_provider}**")

        _has_api_key = bool(os.environ.get(_key_name))
        if not _has_api_key:
            try:
                _has_api_key = _key_name in st.secrets
            except Exception:
                _has_api_key = False

        try:
            _package_installed = importlib.util.find_spec(_package_name) is not None
        except ModuleNotFoundError:
            _package_installed = False

        if not _package_installed:
            _install_name = "requests" if _provider == "gemini" else "openai"
            st.error(f"❌ {_install_name} library not installed")
            st.info(f"Run: `pip install {_install_name}`")
        elif _has_api_key:
            st.success("✅ API key configured")
        else:
            st.error("❌ No API key found")
            st.info(f"Add `{_key_name}` to `.streamlit/secrets.toml`")

    if _hybrid_retrieval_available():
        with st.expander("🧠 Retrieval service", expanded=False):
            st.caption(
                "Hybrid retrieval (exact name + lexical + dense + transcripts) "
                "artifacts are loaded into the running process."
            )
            if st.button("♻️ Clear retrieval caches", use_container_width=True):
                try:
                    from utils.retrieval import clear_retrieval_caches
                    clear_retrieval_caches()
                except Exception as exc:
                    st.warning(f"Could not clear caches: {exc}")
                st.success("Retrieval caches cleared.")
                st.rerun()


# ══════════════════════════════════════════════════════════════════════════════
# EXPORT MODAL
# ══════════════════════════════════════════════════════════════════════════════

if st.session_state.get("show_export"):
    export_lines = [
        "# Legal Chat Transcript",
        f"**Date:** {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        f"**Source:** {selected_source_label}",
        "", "---", ""
    ]
    for msg in st.session_state.chat_messages:
        role = "**You:**" if msg["role"] == "user" else "**Assistant:**"
        export_lines.append(f"{role}\n\n{msg['content']}\n")
        if "cases" in msg:
            export_lines.append("\n**Sources:**")
            for case in msg["cases"]:
                export_lines.append(f"- {case['name']} ({case.get('source', '')})")
        export_lines.append("\n---\n")
    export_text = "\n".join(export_lines)
    st.download_button(
        label="📄 Download as Markdown",
        data=export_text,
        file_name=f"legal_chat_{datetime.now().strftime('%Y%m%d_%H%M')}.md",
        mime="text/markdown",
        key="export_download"
    )
    if st.button("Close", key="close_export"):
        st.session_state.show_export = False
        st.rerun()


# ══════════════════════════════════════════════════════════════════════════════
# HANDLE PENDING FOLLOW-UP
# ══════════════════════════════════════════════════════════════════════════════

if "pending_question" in st.session_state:
    user_input = st.session_state.pending_question
    del st.session_state.pending_question
else:
    user_input = None


# ══════════════════════════════════════════════════════════════════════════════
# CHAT INPUT
# ══════════════════════════════════════════════════════════════════════════════

if not user_input:
    with st.form(key="chat_form", clear_on_submit=True):
        col1, col2 = st.columns([6, 1])
        with col1:
            user_query = st.text_area(
                "Your question:",
                placeholder="Ask about a legal issue...",
                height=100,
                label_visibility="collapsed",
                disabled=st.session_state.chat_query_count >= query_limit,
                key="user_input_field"
            )
        with col2:
            st.write("")
            submit_button = st.form_submit_button("Send 🚀", use_container_width=True)
        if submit_button and user_query and user_query.strip():
            user_input = user_query.strip()


# Search settings + follow-up prompt
with st.container(border=True):
    st.caption(
        # ADAPT: Change year range to match NH dataset
        "Search covers NH Supreme Court cases from **XXXX–present**. "
        "After each answer, you can ask follow-up questions like "
        "*\"What did the dissent say?\"* or *\"How do these cases compare?\"*"
    )

    source_col, cases_col, usage_col = st.columns([3, 2, 2])
    with source_col:
        selected_source_label = st.selectbox(
            "Search in",
            options=list(source_options.keys()),
            index=0,
            key="source_selector",
        )
        st.session_state.chat_source = source_options[selected_source_label]
    with cases_col:
        num_cases = st.slider(
            "Cases to retrieve",
            min_value=3, max_value=10, value=5,
            help="More cases provide broader context but may slow the response.",
            key="chat_num_cases",
        )
    with usage_col:
        st.metric("Queries Used", f"{st.session_state.chat_query_count}/{query_limit}")

    if st.session_state.chat_query_count >= query_limit:
        st.warning("⚠️ Query limit reached for this session. Clear chat to reset.")


# "What can I ask?" expander
with st.expander("ℹ️ What can I ask?", expanded=False):
    st.markdown("""
    **Topic overview** — *"What cases deal with search and seizure?"*

    **Holding / rule** — *"What was the holding in State v. Smith?"*

    **Facts** — *"What are the key facts in State v. Jones?"*

    **Vote split** — *"Was the decision unanimous?"*

    **Opinion author** — *"Who wrote the majority opinion?"* / *"Who dissented?"*

    **Justice alignment** — *"Which justices joined the dissent?"*

    **Comparison** — *"Compare the reasoning in State v. Smith and State v. Jones."*

    **Case lookup** — *"Tell me about State v. Smith."*

    **Date / procedure** — *"When was State v. Smith decided?"*

    **Follow-up** — *"What did the dissent say?"* / *"How do these cases compare?"*
    """)


# ══════════════════════════════════════════════════════════════════════════════
# EXAMPLE QUESTIONS (shown when chat is empty)
# ══════════════════════════════════════════════════════════════════════════════

if not st.session_state.chat_messages:
    st.markdown("### 💡 Example Questions")
    col1, col2 = st.columns(2)
    with col1:
        st.markdown("""
        **Criminal Law:**
        - What cases deal with search and seizure?
        - How has the court ruled on self-incrimination?
        - What are key cases about right to counsel?
        """)
        st.markdown("""
        **Civil Procedure:**
        - What cases address personal jurisdiction?
        - How has the court interpreted standing?
        - What are important summary judgment cases?
        """)
    with col2:
        st.markdown("""
        **Family Law:**
        - What cases address parental rights?
        - How has the court ruled on child custody?
        - What are important adoption cases?
        """)
        st.markdown("""
        **Property & Torts:**
        - How has the court ruled on eminent domain?
        - What cases address premises liability?
        - What are important contract cases?
        """)


# ══════════════════════════════════════════════════════════════════════════════
# DISPLAY CHAT HISTORY
# ══════════════════════════════════════════════════════════════════════════════

# Newest exchanges first, question-before-answer preserved inside each pair
messages = st.session_state.chat_messages
exchanges = []
for i in range(0, len(messages), 2):
    exchanges.append(list(enumerate(messages[i:i + 2], start=i)))

for exchange in reversed(exchanges):
    for i, message in exchange:
        with st.chat_message(message["role"]):
            # Follow-ups first (above narrative) for the latest assistant msg
            if message["role"] == "assistant" and i == len(messages) - 1:
                if message.get("follow_ups"):
                    selected_followup = render_follow_ups(
                        message["follow_ups"], key_suffix=f"history_{i}"
                    )
                    if selected_followup:
                        st.session_state.pending_question = selected_followup
                        st.rerun()

            content = message["content"]
            if message["role"] == "assistant":
                content = normalize_case_links(content)
                message["content"] = content
            st.markdown(content)

            if message["role"] == "assistant" and "cases" in message:
                render_sources(message["cases"], key_suffix=f"history_{i}")


# ══════════════════════════════════════════════════════════════════════════════
# PROCESS USER INPUT
# ══════════════════════════════════════════════════════════════════════════════

if user_input:
    if st.session_state.chat_query_count >= query_limit:
        st.error(f"⚠️ Query limit reached ({query_limit}). Clear chat to continue.")
        st.stop()

    st.session_state.chat_messages.append({"role": "user", "content": user_input})
    with st.chat_message("user"):
        st.markdown(user_input)

    with st.chat_message("assistant"):
        # Lazy imports — heavy retrieval loaded only on Send
        from utils.chat_retriever import (
            build_retrieval_query,
            format_context,
            is_referential_followup,
            merge_retrieved_cases,
            retrieve_cases,
        )

        # Build conversation-aware retrieval
        previous_question = ""
        previous_cases = []
        for message in reversed(st.session_state.chat_messages[:-1]):
            if message["role"] == "assistant" and not previous_cases:
                previous_cases = message.get("cases", [])
            elif message["role"] == "user":
                previous_question = message["content"]
                break
        referential = is_referential_followup(user_input)
        retrieval_query = build_retrieval_query(user_input, previous_question, previous_cases)

        # Retrieve cases
        hybrid_diagnostics: Dict = {}
        with st.spinner("🔍 Searching cases..."):
            previous_case_names = [c.get("name", "") for c in previous_cases if c.get("name")]
            fresh_cases: List[Dict] = []
            if _hybrid_retrieval_available():
                fresh_cases, hybrid_diagnostics = _retrieve_via_hybrid(
                    user_input, previous_case_names, num_cases,
                )
            if not fresh_cases:
                fresh_cases = retrieve_cases(
                    retrieval_query,
                    source=st.session_state.chat_source,
                    top_k=num_cases,
                )
            retrieved_cases = merge_retrieved_cases(
                fresh_cases,
                previous_cases,
                include_previous=referential,
                max_cases=num_cases * 2,
            )

        if not retrieved_cases:
            st.warning("No relevant cases found. Try rephrasing your question.")
            st.stop()

        # Optional retrieval diagnostics
        if hybrid_diagnostics:
            debug_env = os.environ.get("CHAT_DEBUG_RETRIEVAL", "").lower()
            expanded = debug_env in {"1", "true", "yes"}
            with st.expander("🧬 Retrieval details", expanded=expanded):
                plan = hybrid_diagnostics.get("plan")
                if plan is not None:
                    st.caption("Detected intents: " + ", ".join(str(i) for i in plan.intents))
                    st.caption("Requested fields: " + (", ".join(plan.requested_fields) or "—"))
                st.caption("Sufficient: " + f"{hybrid_diagnostics.get('sufficient')}")
                st.caption("Missing fields: " + (", ".join(hybrid_diagnostics.get("missing_fields", [])) or "none"))
                latency = hybrid_diagnostics.get("latency", {}) or {}
                if latency:
                    st.caption("Latency (ms): " + str(latency))
                top_cases = (hybrid_diagnostics.get("fused_trace") or {}).get("top_cases", [])
                if top_cases:
                    with st.container(border=True):
                        for entry in top_cases[:num_cases]:
                            st.write(
                                f"- {entry.get('name')} "
                                f"(rrf={entry.get('rrf')}; "
                                f"backends={entry.get('backends')})"
                            )

        # Format LLM context
        if hybrid_diagnostics and hybrid_diagnostics.get("context"):
            case_context = hybrid_diagnostics["context"]
        else:
            case_context = format_context(retrieved_cases)

        # Build conversation history (last 5 exchanges)
        conversation_history = []
        for msg in st.session_state.chat_messages[-11:-1]:
            conversation_history.append({"role": msg["role"], "content": msg["content"]})

        # Generate response
        with st.spinner("💭 Thinking..."):
            try:
                from utils.chat_provider import generate_chat_response
                response_stream = generate_chat_response(
                    user_message=user_input,
                    case_context=case_context,
                    conversation_history=conversation_history,
                    stream=True
                )

                response_placeholder = st.empty()
                if isinstance(response_stream, str):
                    response_text = response_stream
                    response_placeholder.markdown(response_text)
                else:
                    chunks = []
                    for chunk in response_stream:
                        if chunk:
                            chunks.append(chunk)
                            response_placeholder.markdown("".join(chunks) + " ▌")
                    response_text = "".join(chunks)

                formatted_response = format_with_links(response_text, retrieved_cases)
                response_placeholder.markdown(formatted_response)
                render_sources(retrieved_cases, key_suffix="current")

                # Case-specific follow-up suggestions
                case_names = [c.get("name", "") for c in retrieved_cases if c.get("name") and c.get("name") != "Error"]
                primary_case = case_names[0] if case_names else "the leading case"
                second_case = case_names[1] if len(case_names) > 1 else None
                follow_ups = [f"What were the key facts in {primary_case}?"]
                if second_case:
                    follow_ups.extend([
                        f"Compare the reasoning in {primary_case} and {second_case}.",
                        f"How do the holdings in {primary_case} and {second_case} differ?",
                    ])
                else:
                    follow_ups.extend([
                        f"What rule did {primary_case} establish?",
                        f"What did the dissent say in {primary_case}?",
                    ])

                st.session_state.chat_messages.append({
                    "role": "assistant",
                    "content": formatted_response,
                    "cases": retrieved_cases,
                    "follow_ups": follow_ups,
                })
                st.session_state.chat_query_count += 1
                st.rerun()

            except Exception as e:
                st.error(f"⚠️ Error generating response: {e}")
                st.info("Please check your API configuration and try again.")


# ══════════════════════════════════════════════════════════════════════════════
# FOOTER
# ══════════════════════════════════════════════════════════════════════════════

st.divider()
st.caption("""
ℹ️ **Disclaimer:** This assistant provides information about legal cases for educational purposes.
It is not a substitute for professional legal advice. Always consult a qualified attorney for legal matters.
""")
```

---

### 4B. Chat Retriever

**File:** `utils/chat_retriever.py`

This is the core retrieval module. Key components:

1. **`CaseRetriever` class** — wraps TF-IDF search for supreme-court and nh-supreme-court sources
2. **`is_referential_followup()`** — detects referential patterns
3. **`build_retrieval_query()`** — expands referential follow-ups with prior context
4. **`merge_retrieved_cases()`** — deduplicates by href, retains prior cases
5. **`format_context_for_llm()`** — builds labeled evidence blocks with Facts, Question, Holding

**NH adaptation:** You mainly need to change:
- The NH search path in `_build_nh_index()` (already points to `nh-supreme-court/data/processed/opinions.csv`)
- The column names if they differ from `case_name`, `plain_text_summary`, etc.
- The NH case URL routing

Full code:

```python
"""
Multi-source case retrieval for legal chatbox.
Supports Supreme Court, NH Supreme Court, and combined search.
"""
import html
import json
import re
from typing import List, Dict, Optional
from pathlib import Path
import pandas as pd
import streamlit as st
from urllib.parse import quote_plus

# Import existing search for Supreme Court
try:
    from utils.text_search import search as supreme_search, is_available as supreme_available
    SUPREME_SEARCH_AVAILABLE = True
except ImportError:
    SUPREME_SEARCH_AVAILABLE = False


class CaseRetriever:
    def __init__(self, repo_root: Optional[Path] = None):
        if repo_root is None:
            self.repo_root = Path(__file__).resolve().parent.parent
        else:
            self.repo_root = Path(repo_root)
        self._nh_vectorizer = None
        self._nh_matrix = None
        self._nh_index_df = None
        self._supreme_detail_by_href = None

    def retrieve_cases(self, query: str, source: str = "supreme-court", top_k: int = 5) -> List[Dict]:
        if source == "supreme-court":
            return self._search_supreme_court(query, top_k)
        elif source == "nh-supreme-court":
            return self._search_nh_court(query, top_k)
        elif source == "both":
            supreme_results = self._search_supreme_court(query, top_k)
            nh_results = self._search_nh_court(query, top_k)
            combined = supreme_results + nh_results
            combined.sort(key=lambda x: x.get("score", 0), reverse=True)
            return combined[:top_k * 2]
        else:
            raise ValueError(f"Unknown source: {source}")

    def _search_supreme_court(self, query: str, top_k: int) -> List[Dict]:
        if not SUPREME_SEARCH_AVAILABLE or not supreme_available():
            return [{
                "name": "Error",
                "source": "supreme-court",
                "snippet": "Supreme Court search not available. Check data files.",
                "score": 0,
            }]
        try:
            results = supreme_search(query, top_k=top_k)
            enhanced = []
            for r in results:
                case = {
                    "name": r.get("name", "Unknown"),
                    "source": "supreme-court",
                    "term": r.get("term"),
                    "docket_number": r.get("docket_number", ""),
                    "score": r.get("score", 0),
                    "href": r.get("href", ""),
                }
                case.update(self._get_supreme_court_detail(r.get("href", "")))
                case_name = r.get('name', '')
                encoded_name = quote_plus(case_name)
                case["url"] = f"/Cases?q={encoded_name}&case={encoded_name}"
                enhanced.append(case)
            return enhanced
        except Exception as e:
            st.warning(f"Supreme Court search error: {e}")
            return []

    def _search_nh_court(self, query: str, top_k: int) -> List[Dict]:
        # ADAPT: This method is already NH-aware. Update column names if needed.
        if self._nh_vectorizer is None:
            self._build_nh_index()
        if self._nh_index_df is None or self._nh_index_df.empty:
            return [{
                "name": "Error",
                "source": "nh-supreme-court",
                "snippet": "NH Supreme Court data not available.",
                "score": 0,
            }]
        try:
            from sklearn.metrics.pairwise import cosine_similarity
            q_vec = self._nh_vectorizer.transform([query.lower()])
            scores = cosine_similarity(q_vec, self._nh_matrix).flatten()
            top_idx = scores.argsort()[::-1][:top_k]
            results = []
            for i in top_idx:
                score = float(scores[i])
                if score < 0.01:
                    break
                row = self._nh_index_df.iloc[i]
                case = {
                    # ADAPT: Update column names to match NH CSV
                    "name": row.get("case_name", "Unknown"),
                    "source": "nh-supreme-court",
                    "year": row.get("term_year"),
                    "docket_number": row.get("case_number", ""),
                    "score": round(score, 4),
                    "snippet": self._truncate_text(row.get("plain_text_summary", ""), 300),
                    "outcome": row.get("outcome", ""),
                    "author": row.get("author", ""),
                    # ADAPT: Change to NH case page route
                    "url": "01_Opinions.py",
                }
                results.append(case)
            return results
        except Exception as e:
            st.warning(f"NH Court search error: {e}")
            return []

    def _build_nh_index(self):
        # ADAPT: Update path and column names for NH data
        try:
            from sklearn.feature_extraction.text import TfidfVectorizer
            parent_dir = self.repo_root.parent
            nh_opinions_path = parent_dir / "nh-supreme-court" / "data" / "processed" / "opinions.csv"
            if not nh_opinions_path.exists():
                return
            df = pd.read_csv(nh_opinions_path)

            def _combine_text(row):
                # ADAPT: Include NH-specific text columns
                parts = [
                    str(row.get("case_name", "")),
                    str(row.get("plain_text_summary", "")),
                    str(row.get("rsa_citations", "")),
                ]
                return " ".join(p for p in parts if p and p != "nan").lower()

            df["_search_text"] = df.apply(_combine_text, axis=1)
            df = df[df["_search_text"].str.len() > 20].reset_index(drop=True)
            vectorizer = TfidfVectorizer(
                max_features=20_000, ngram_range=(1, 2),
                min_df=2, sublinear_tf=True, stop_words="english",
            )
            matrix = vectorizer.fit_transform(df["_search_text"])
            self._nh_vectorizer = vectorizer
            self._nh_matrix = matrix
            self._nh_index_df = df
        except Exception:
            pass

    # ── Detail loading (for Supreme Court data) ────────────────────────────
    # ADAPT: For NH, replace _load_supreme_court_details / _get_supreme_court_detail
    # with NH-specific detail loading. The method below is the pattern.

    @staticmethod
    def _clean_text(value) -> str:
        if value is None or pd.isna(value):
            return ""
        text = html.unescape(re.sub(r"<[^>]+>", " ", str(value)))
        return re.sub(r"\s+", " ", text).strip()

    def _load_supreme_court_details(self) -> Dict[str, Dict]:
        if self._supreme_detail_by_href is not None:
            return self._supreme_detail_by_href
        self._supreme_detail_by_href = {}
        try:
            detail_path = self.repo_root / "data" / "case_detail.parquet"
            if not detail_path.exists():
                return self._supreme_detail_by_href
            columns = ["href", "facts_of_the_case", "question", "conclusion", "description", "decisions"]
            df = pd.read_parquet(detail_path, columns=columns)
            self._supreme_detail_by_href = {
                row["href"]: row.to_dict()
                for _, row in df.iterrows()
                if self._clean_text(row.get("href"))
            }
        except Exception:
            pass
        return self._supreme_detail_by_href

    def _get_supreme_court_detail(self, href: str) -> Dict[str, str]:
        row = self._load_supreme_court_details().get(href, {})
        facts = self._clean_text(row.get("facts_of_the_case"))
        question = self._clean_text(row.get("question"))
        holding = self._clean_text(row.get("conclusion"))
        description = self._clean_text(row.get("description"))
        detail = {
            "facts": self._truncate_text(facts, 900),
            "question": self._truncate_text(question, 500),
            "holding": self._truncate_text(holding, 900),
            "description": self._truncate_text(description, 500),
            "snippet": self._truncate_text(facts or question or description, 300),
        }
        detail.update(self._summarize_decisions(row.get("decisions")))
        return detail

    @staticmethod
    def _summarize_decisions(value) -> Dict[str, str]:
        if value is None or (isinstance(value, float) and pd.isna(value)):
            return {}
        try:
            decisions = json.loads(value) if isinstance(value, str) else value
        except (TypeError, json.JSONDecodeError):
            return {}
        if not isinstance(decisions, (list, tuple)):
            return {}
        for decision in decisions:
            if not isinstance(decision, dict):
                continue
            votes = decision.get("votes") or []
            majority, minority = [], []
            opinion_authors = []
            majority_authors, dissent_authors, concurrence_authors = [], [], []
            for vote in votes:
                if not isinstance(vote, dict):
                    continue
                name = (vote.get("member") or {}).get("name")
                side = (vote.get("vote") or "").lower()
                opinion_type = (vote.get("opinion_type") or "").lower()
                if not name:
                    continue
                if side in ("majority", "concurrence"):
                    majority.append(name)
                elif side in ("minority", "dissent"):
                    minority.append(name)
                if opinion_type not in ("", "none"):
                    opinion_authors.append(f"{opinion_type}: {name}")
                    if opinion_type in ("majority", "plurality"):
                        majority_authors.append(name)
                    elif "dissent" in opinion_type:
                        dissent_authors.append(name)
                    elif "concurr" in opinion_type:
                        concurrence_authors.append(name)
            if majority or minority:
                summary = {
                    "vote_split": f"{len(majority)}-{len(minority)}",
                    "majority_justices": ", ".join(majority),
                    "minority_justices": ", ".join(minority),
                }
                if opinion_authors:
                    summary["opinion_authors"] = "; ".join(opinion_authors)
                if majority_authors:
                    summary["majority_opinion_authors"] = ", ".join(majority_authors)
                if dissent_authors:
                    summary["dissent_authors"] = ", ".join(dissent_authors)
                if concurrence_authors:
                    summary["concurrence_authors"] = ", ".join(concurrence_authors)
                return summary
        return {}

    def _truncate_text(self, text: str, max_chars: int) -> str:
        if not text or len(text) <= max_chars:
            return text
        truncated = text[:max_chars]
        last_period = truncated.rfind(". ")
        if last_period > max_chars * 0.7:
            return truncated[:last_period + 1]
        return truncated + "..."

    def format_context_for_llm(self, cases: List[Dict]) -> str:
        if not cases:
            return "No relevant cases found."
        context_parts = []
        for i, case in enumerate(cases, 1):
            # ADAPT: Change source label for NH
            source_label = "NH Supreme Court" if case["source"] == "nh-supreme-court" else "U.S. Supreme Court"
            entry = f"**Case {i}: {case['name']}**\n"
            entry += f"Court: {source_label}\n"
            if case.get("term"):
                entry += f"Term: {case['term']}\n"
            elif case.get("year"):
                entry += f"Year: {case['year']}\n"
            if case.get("docket_number"):
                entry += f"Docket: {case['docket_number']}\n"
            if case.get("outcome"):
                entry += f"Outcome: {case['outcome']}\n"
            if case.get("facts"):
                entry += f"\nFacts: {case['facts']}\n"
            if case.get("question"):
                entry += f"Question: {case['question']}\n"
            # Holding field: show "Not available" rather than None/nan
            entry += f"Holding: {case.get('holding') or 'Not available in the supplied case record.'}\n"
            if case.get("vote_split"):
                entry += f"Vote split: {case['vote_split']}\n"
            if case.get("majority_justices"):
                entry += f"Majority: {case['majority_justices']}\n"
            if case.get("minority_justices"):
                entry += f"Minority/dissent: {case['minority_justices']}\n"
            if case.get("opinion_authors"):
                entry += f"Opinion author(s): {case['opinion_authors']}\n"
            if case.get("description"):
                entry += f"Description: {case['description']}\n"
            elif case.get("snippet") and not case.get("facts"):
                entry += f"Summary: {case['snippet']}\n"
            context_parts.append(entry)
        return "\n\n".join(context_parts)


# ── Module-level convenience functions ───────────────────────────────────────

@st.cache_resource
def get_retriever() -> CaseRetriever:
    return CaseRetriever()


def retrieve_cases(query: str, source: str = "supreme-court", top_k: int = 5) -> List[Dict]:
    retriever = get_retriever()
    return retriever.retrieve_cases(query, source, top_k)


def format_context(cases: List[Dict]) -> str:
    retriever = get_retriever()
    return retriever.format_context_for_llm(cases)


# ── Referential follow-up detection ──────────────────────────────────────────

_REFERENTIAL_PATTERNS = (
    r"\b(?:these|those)\s+(?:cases?|holdings?|decisions?|rules?)\b",
    r"\bthat\s+(?:case|holding|decision|rule)\b",
    r"\bthe\s+(?:dissent|majority|first|second|last)\b",
    r"\blater\s+decisions?\b",
    r"\bhow\s+(?:did|do)\s+(?:it|they|these|those)\b",
)


def is_referential_followup(question: str) -> bool:
    """Conservatively identify a question that depends on prior context."""
    text = question.strip().lower()
    return bool(text) and any(re.search(pattern, text) for pattern in _REFERENTIAL_PATTERNS)


def build_retrieval_query(
    question: str,
    previous_question: str = "",
    previous_cases: Optional[List[Dict]] = None,
) -> str:
    """Expand only referential follow-ups; preserve standalone queries verbatim."""
    if not is_referential_followup(question):
        return question
    parts = [f"Current question: {question}"]
    if previous_question:
        parts.append(f"Previous topic: {previous_question}")
    case_names = [
        case.get("name", "").strip()
        for case in (previous_cases or [])
        if case.get("name") and case.get("name") != "Error"
    ]
    if case_names:
        parts.append("Cases: " + "; ".join(case_names))
    return "\n".join(parts)


def merge_retrieved_cases(
    newly_retrieved: List[Dict],
    previous_cases: Optional[List[Dict]] = None,
    include_previous: bool = False,
    max_cases: Optional[int] = None,
) -> List[Dict]:
    """Deduplicate cases by href while retaining prior referenced material."""
    candidates = list(previous_cases or []) + list(newly_retrieved) if include_previous else list(newly_retrieved)
    merged = []
    seen = set()
    for case in candidates:
        key = case.get("href") or (case.get("source"), case.get("name"))
        if key in seen:
            continue
        seen.add(key)
        merged.append(case)
        if max_cases is not None and len(merged) >= max_cases:
            break
    return merged
```

---

### 4C. Chat Formatter

**File:** `utils/chat_formatter.py`

Handles:
- Converting `*Case Name*` italics in LLM responses to `[Case Name](/Cases?...)` markdown links
- Normalizing legacy link formats
- Generating narrative text when the provider returns empty
- Rendering case source cards with View buttons
- Rendering follow-up question buttons

**NH adaptation:** Change the URL route from `/Cases` to the NH case page route. The `normalize_case_links` regex needs updating.

```python
"""
Format LLM responses with clickable case links and styled components.
"""
import re
from typing import List, Dict, Optional
import streamlit as st


class ResponseFormatter:
    def __init__(self):
        self.case_link_pattern = re.compile(r'\*([A-Z][^*]+v\.\s+[^*]+)\*')

    def format_response_with_links(self, response_text: str, retrieved_cases: List[Dict]) -> str:
        case_map = {}
        for case in retrieved_cases:
            case_name = case.get("name", "")
            url = case.get("url", "")
            if case_name and url:
                case_map[case_name.lower()] = (case_name, url)

        def replace_citation(match):
            cited_name = match.group(1)
            cited_lower = cited_name.lower()
            for key, (original_name, url) in case_map.items():
                if key in cited_lower or cited_lower in key:
                    return f"[*{cited_name}*]({url})"
            return f"*{cited_name}*"

        formatted = self.case_link_pattern.sub(replace_citation, response_text)
        return self.normalize_case_links(formatted)

    @staticmethod
    def normalize_case_links(response_text: str) -> str:
        # ADAPT: If NH uses a different route, update the regex
        # US Supreme: /1_Cases.py?q=... or /?q=... → /Cases?q=...
        # NH example: /01_Opinions.py?q=... → /Opinions?q=...
        if not response_text:
            return response_text
        return re.sub(
            r"\]\((?:/?1_Cases(?:\.py)?|/?)\?(q=[^)]+)\)",
            r"](/Cases?\1)",
            response_text,
        )

    # ── Narrative fallback when provider returns empty ─────────────────────

    def ensure_narrative(self, response_text: str, retrieved_cases: List[Dict]) -> str:
        text = (response_text or "").strip()
        provider_error = text.startswith("⚠️")
        if text and not provider_error:
            return text
        usable = [case for case in retrieved_cases if case.get("name") and case.get("name") != "Error"]
        if not usable:
            return "I couldn't find enough case material to answer that question. Try rephrasing it."
        lead = "The most relevant cases in the collection are "
        citations = []
        for case in usable:
            name = case["name"]
            year = case.get("term") or case.get("year")
            citations.append(f"*{name}*" + (f" ({year})" if year else ""))
        narrative = lead + ", ".join(citations[:-1])
        if len(citations) > 1:
            narrative += f", and {citations[-1]}"
        else:
            narrative += citations[0]
        narrative += ". Open the source summaries below for the facts and legal questions available in the case data."
        return narrative

    # ── Source cards ────────────────────────────────────────────────────────

    def render_case_card(self, case: Dict, key_suffix: str = "") -> None:
        # ADAPT: Change emoji / label for NH
        source_emoji = "⚖️"
        source_label = "NH Supreme Court"

        with st.container(border=True):
            col1, col2 = st.columns([5, 1])
            with col1:
                st.markdown(f"### {source_emoji} {case['name']}")
                badges = []
                if case.get("term"):
                    badges.append(f"📅 {case['term']} Term")
                elif case.get("year"):
                    badges.append(f"📅 {case['year']}")
                if case.get("outcome"):
                    badges.append(f"⚖️ {case['outcome']}")
                if case.get("author"):
                    badges.append(f"✍️ {case['author']}")
                if badges:
                    st.caption(" • ".join(badges))
                if case.get("snippet"):
                    with st.expander("📄 Case Summary", expanded=False):
                        st.write(case["snippet"])
            with col2:
                if case.get("url"):
                    case_name = case.get("name", "")
                    button_key = f"view_case_{key_suffix}_{case_name[:20].replace(' ', '_')}"
                    if st.button("View →", key=button_key, type="primary"):
                        # ADAPT: Update page route for NH
                        st.session_state["search_query"] = case_name
                        st.session_state["_chat_selected_case"] = case_name
                        st.switch_page("pages/1_Cases.py")  # CHANGE for NH

    def render_sources_section(self, cases: List[Dict], key_suffix: str = "") -> None:
        with st.expander(f"📚 Sources ({len(cases)} cases)", expanded=False):
            for i, case in enumerate(cases):
                self.render_case_card(case, key_suffix=f"{key_suffix}_{i}")
                if i < len(cases) - 1:
                    st.divider()

    # ── Follow-up buttons ───────────────────────────────────────────────────

    def render_follow_up_buttons(self, questions: List[str], key_suffix: str = "") -> Optional[str]:
        if not questions:
            return None
        st.markdown("#### 💡 Follow-up Questions")
        for i, question in enumerate(questions):
            if st.button(
                question,
                key=f"followup_{key_suffix}_{i}",
                use_container_width=True,
            ):
                return question
        return None


# ── Singleton + convenience functions ────────────────────────────────────────

_formatter = None

def get_formatter() -> ResponseFormatter:
    global _formatter
    if _formatter is None:
        _formatter = ResponseFormatter()
    return _formatter


def format_with_links(response_text: str, cases: List[Dict]) -> str:
    formatter = get_formatter()
    narrative = formatter.ensure_narrative(response_text, cases)
    return formatter.format_response_with_links(narrative, cases)


def normalize_case_links(response_text: str) -> str:
    return get_formatter().normalize_case_links(response_text)


def render_sources(cases: List[Dict], key_suffix: str = "") -> None:
    get_formatter().render_sources_section(cases, key_suffix)


def render_follow_ups(questions: List[str], key_suffix: str = "") -> Optional[str]:
    return get_formatter().render_follow_up_buttons(questions, key_suffix)
```

---

### 4D. Chat Provider

**File:** `utils/chat_provider.py` — **Copy verbatim**, no NH-specific changes.

```python
"""Provider selector. Gemini is default; OpenCode is opt-in backup only."""
from __future__ import annotations
import os
import streamlit as st
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env"))

SUPPORTED_PROVIDERS = {"gemini", "opencode"}

def provider_name() -> str:
    configured = os.environ.get("CHAT_PROVIDER")
    if not configured:
        try:
            configured = st.secrets.get("CHAT_PROVIDER")
        except Exception:
            configured = None
    name = (configured or "gemini").strip().lower()
    if name not in SUPPORTED_PROVIDERS:
        raise ValueError(f"Unsupported CHAT_PROVIDER '{name}'. Use: gemini or opencode.")
    return name

def generate_chat_response(*args, **kwargs):
    name = provider_name()
    if name == "gemini":
        from utils.gemini_chat import generate_chat_response as generate
    else:
        from utils.opencode_chat import generate_chat_response as generate
    return generate(*args, **kwargs)
```

---

### 4E. Gemini Provider

**File:** `utils/gemini_chat.py` — **Copy verbatim**. Uses Google's REST/SSE API with `gemini-2.5-flash`. No NH-specific changes.

---

### 4F. OpenCode Backup

**File:** `utils/opencode_chat.py` — **Copy verbatim**. Uses OpenAI-compatible client pointing to `opencode.ai/zen/go/v1`. No NH-specific changes.

---

## 5. Hybrid Retrieval Package

**Directory:** `utils/retrieval/`

This package is the advanced version of the retrieval system. It's fully optional — the chat works with just the legacy TF-IDF retriever. But if you want better results, deploy these artifacts.

Most files can be copied verbatim. The ones needing NH adaptation are:
- `service.py` — data paths and column names
- `metadata.py` — field mapping from NH data format to `CaseEvidence`
- `query_analyzer.py` — optional, if NH has different query intents

### 5A. Models

**File:** `utils/retrieval/models.py` — **Copy verbatim**.

```python
"""Typed contracts for the hybrid retrieval pipeline."""
from __future__ import annotations
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Literal

class Intent(StrEnum):
    CASE_LOOKUP = "case_lookup"
    TOPIC_OVERVIEW = "topic_overview"
    HOLDING = "holding"
    FACTS = "facts"
    VOTE_SPLIT = "vote_split"
    OPINION_AUTHOR = "opinion_author"
    JUSTICE_ALIGNMENT = "justice_alignment"
    COMPARISON = "comparison"
    TRANSCRIPT = "transcript"
    DATE_OR_PROCEDURE = "date_or_procedure"
    OTHER = "other"

@dataclass(frozen=True)
class QueryPlan:
    raw_query: str
    retrieval_query: str
    intents: tuple[Intent, ...]
    named_cases: tuple[str, ...] = ()
    citations: tuple[str, ...] = ()
    dockets: tuple[str, ...] = ()
    speakers: tuple[str, ...] = ()
    requested_fields: tuple[str, ...] = ()
    requires_transcripts: bool = False
    include_prior_cases: bool = False

@dataclass(frozen=True)
class RetrievalHit:
    document_id: str
    case_id: str
    source: Literal["case", "transcript", "exact"]
    rank: int
    score: float
    backend: str
    text: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

@dataclass
class CaseEvidence:
    case_id: str
    name: str
    href: str
    term: str = ""
    docket_number: str = ""
    citation: str = ""
    facts: str = ""
    question: str = ""
    holding: str = ""
    description: str = ""
    vote_split: str = ""
    majority_justices: list[str] = field(default_factory=list)
    minority_justices: list[str] = field(default_factory=list)
    majority_authors: list[str] = field(default_factory=list)
    dissent_authors: list[str] = field(default_factory=list)
    concurrence_authors: list[str] = field(default_factory=list)
    transcript_passages: list[dict[str, Any]] = field(default_factory=list)
    retrieval_trace: list[RetrievalHit] = field(default_factory=list)

@dataclass(frozen=True)
class RetrievalResponse:
    plan: QueryPlan
    cases: tuple[CaseEvidence, ...]
    sufficient: bool
    missing_fields: tuple[str, ...]
    diagnostics: dict[str, Any]
```

---

### 5B. Query Analyzer

**File:** `utils/retrieval/query_analyzer.py` — **Copy verbatim** (or adapt NH-specific patterns).

```python
"""Deterministic query analysis."""
from __future__ import annotations
import re
from .models import Intent, QueryPlan

FIELD_PATTERNS: dict[str, tuple[Intent, str]] = {
    "holding": (Intent.HOLDING, r"\b(?:hold|holding|rule|decide[ds]?|decision(?!\s+split))\b"),
    "facts": (Intent.FACTS, r"\b(?:facts?|happened|background|what happened)\b"),
    "vote_split": (Intent.VOTE_SPLIT, r"\b(?:vote|split|unanimous|decision split|[0-9]+-[0-9]+)\b"),
    "opinion_authors": (
        Intent.OPINION_AUTHOR,
        r"\b(?:who wrote|author(?:ed)?|wrote the (?:majority |dissenting )?opinion|"
        r"majority opinion|dissent(?:ing)? opinion|concurrence)\b",
    ),
    "justice_alignment": (
        Intent.JUSTICE_ALIGNMENT,
        r"\b(?:which justices|who joined|majority justices|dissenters?|"
        r"who dissented|who was in the majority)\b",
    ),
    "transcript_passages": (
        Intent.TRANSCRIPT,
        r"\b(?:oral argument|transcript transcription|oral argument transcript|"
        r"asked during argument|questioned during oral argument|exchange during argument|"
        r"argue during oral argument|what did .* justice .* ask|what did .* say during oral argument)\b",
    ),
    "date_or_procedure": (
        Intent.DATE_OR_PROCEDURE,
        r"\b(?:argued|decided|date|procedural|lower court|docket|when did)\b",
    ),
}

CITATION_RE = re.compile(r"\b\d+\s+U\.S\.\s+\d+\b", re.I)
DOCKET_RE = re.compile(r"\b(?:No\.\s*)?\d{1,2}-\d{2,5}\b", re.I)

_COMPARISON_RE = re.compile(
    r"\b(?:compare|difference|differ|differences|versus|vs\.|changed|overruled|"
    r"over time|line of cases)\b"
)
_REFERENTIAL_RE = re.compile(
    r"\b(?:that case|those cases|the dissent|the majority|the opinion|"
    r"they|these decisions|those decisions|later cases?)\b"
)
_PARTY_HINT_RE = re.compile(r"\b([A-Z][A-Za-z'\-]+)\s+v\.?\s+([A-Z][A-Za-z'\-]+)")
_SINGLE_PARTY_RE = re.compile(r"\b([A-Z][A-Za-z'\-]{3,})\b")

def _named_cases(query: str) -> tuple[str, ...]:
    candidates: list[str] = []
    for match in _PARTY_HINT_RE.finditer(query):
        left = match.group(1)
        right = match.group(2)
        if left and right:
            candidates.append(f"{left} v. {right}")
    return tuple(dict.fromkeys(candidates))

def analyze_query(query: str, previous_cases: tuple[str, ...] = ()) -> QueryPlan:
    if not query:
        query = ""
    lowered = query.casefold()
    intents: list[Intent] = []
    requested: list[str] = []
    for field, (intent, pattern) in FIELD_PATTERNS.items():
        if re.search(pattern, lowered):
            if intent not in intents:
                intents.append(intent)
            if field not in requested:
                requested.append(field)
    if _PARTY_HINT_RE.search(query) or _SINGLE_PARTY_RE.search(query):
        if Intent.CASE_LOOKUP not in intents:
            intents.append(Intent.CASE_LOOKUP)
    if not intents:
        intents.append(Intent.TOPIC_OVERVIEW)
    comparative = bool(_COMPARISON_RE.search(lowered))
    if comparative and Intent.COMPARISON not in intents:
        intents.append(Intent.COMPARISON)
    referential = bool(_REFERENTIAL_RE.search(lowered))
    include_prior = referential and bool(previous_cases)
    if referential and include_prior and Intent.TOPIC_OVERVIEW not in intents:
        intents.append(Intent.TOPIC_OVERVIEW)
    citations = tuple(CITATION_RE.findall(query))
    dockets = tuple(DOCKET_RE.findall(query))
    named = _named_cases(query)
    retrieval_query = query
    if include_prior and previous_cases:
        retrieval_query = f"{query}\nPrior cases: {', '.join(previous_cases)}"
    return QueryPlan(
        raw_query=query,
        retrieval_query=retrieval_query,
        intents=tuple(intents),
        named_cases=named,
        citations=citations,
        dockets=dockets,
        speakers=(),
        requested_fields=tuple(requested),
        requires_transcripts=Intent.TRANSCRIPT in intents,
        include_prior_cases=include_prior,
    )
```

---

### 5C–5N (Remaining Retrieval Modules)

These files can be **copied verbatim** from the source repo with minimal or no changes:

| Module | Changes Needed |
|---|---|
| `exact_index.py` | None — data-format-agnostic |
| `lexical_index.py` | None — uses generic `retrieval_text` column |
| `dense_index.py` | None — data-format-agnostic |
| `fusion.py` | None — pure math |
| `metadata.py` | **Rewrite** — maps raw data columns → `CaseEvidence` fields |
| `context_builder.py` | None — uses `CaseEvidence` fields |
| `sufficiency.py` | None — uses `CaseEvidence` fields |
| `transcript_index.py` | **Skip** unless NH has oral argument transcripts |
| `diagnostics.py` | None |
| `normalize.py` | None |
| `legacy_adapter.py` | None |
| `service.py` | **Adapt** — data paths, column names |

---

## 6. Referential Follow-Up Detection

**Location:** `utils/chat_retriever.py:422-434`

Patterns that trigger referential expansion:

```python
_REFERENTIAL_PATTERNS = (
    r"\b(?:these|those)\s+(?:cases?|holdings?|decisions?|rules?)\b",  # "these cases", "those holdings"
    r"\bthat\s+(?:case|holding|decision|rule)\b",                     # "that case", "that holding"
    r"\bthe\s+(?:dissent|majority|first|second|last)\b",              # "the dissent", "the majority"
    r"\blater\s+decisions?\b",                                         # "later decisions"
    r"\bhow\s+(?:did|do)\s+(?:it|they|these|those)\b",                # "how did it", "how do they"
)
```

To add more patterns, extend the tuple. Default is intentionally conservative to avoid false positives on standalone questions like "What does the First Amendment protect?" (no match).

---

## 7. Conversation-Aware Retrieval

**Location:** `utils/chat_retriever.py:437-456`

For standalone questions, the retrieval query is the user's question verbatim:

```python
"What are the major exclusionary-rule cases?"
# → sent to search unchanged
```

For referential follow-ups, the query is expanded with prior context:

```python
Current: "Which later decisions expanded or limited these holdings?"
Previous topic: "What are the major exclusionary-rule cases?"
Cases: Weeks v. United States; Mapp v. Ohio; United States v. Leon
# → sent to search as the concatenated string
```

The original user wording is always sent to the LLM — only the search query is expanded.

---

## 8. Case Merging & Deduplication

**Location:** `utils/chat_retriever.py:459-477`

```python
def merge_retrieved_cases(
    newly_retrieved: List[Dict],
    previous_cases: Optional[List[Dict]] = None,
    include_previous: bool = False,       # True only for referential follow-ups
    max_cases: Optional[int] = None,      # e.g., num_cases * 2
) -> List[Dict]:
```

- Deduplicates by `href` (primary) or `(source, name)` tuple (fallback)
- When `include_previous=True`, prior cases are prepended before fresh results
- Deduplication preserves first occurrence, so prior referenced cases are kept even when fresh TF-IDF differs

---

## 9. Follow-Up Suggestions

**Location:** `pages/14_Chat.py:543-556`

Generated locally (no model call) using actual retrieved case names:

```python
case_names = [c.get("name", "") for c in retrieved_cases if c.get("name") and c.get("name") != "Error"]
primary_case = case_names[0] if case_names else "the leading case"
second_case = case_names[1] if len(case_names) > 1 else None

follow_ups = [f"What were the key facts in {primary_case}?"]
if second_case:
    follow_ups.extend([
        f"Compare the reasoning in {primary_case} and {second_case}.",
        f"How do the holdings in {primary_case} and {second_case} differ?",
    ])
else:
    follow_ups.extend([
        f"What rule did {primary_case} establish?",
        f"What did the dissent say in {primary_case}?",
    ])
```

---

## 10. Tests

### `tests/test_chat_conversation.py` — **Copy verbatim** (imports from `utils.chat_retriever`)

Tests all the retrieval logic without calling any provider:

```python
from utils.chat_retriever import (
    CaseRetriever,
    build_retrieval_query,
    merge_retrieved_cases,
)

CASES = [
    {"name": "Mapp v. Ohio", "href": "mapp", "source": "supreme-court"},
    {"name": "Weeks v. United States", "href": "weeks", "source": "supreme-court"},
]

def test_standalone_question_is_not_rewritten():
    question = "What cases established the exclusionary rule?"
    assert build_retrieval_query(question, "old topic", CASES) == question

def test_referential_followup_includes_previous_topic_and_cases():
    query = build_retrieval_query("What did the dissent say?", "Explain the exclusionary rule.", CASES)
    assert "Explain the exclusionary rule" in query
    assert "Mapp v. Ohio" in query
    assert "Weeks v. United States" in query

def test_prior_and_new_cases_are_deduplicated_by_href():
    fresh = [CASES[0].copy(), {"name": "United States v. Leon", "href": "leon"}]
    merged = merge_retrieved_cases(fresh, CASES, include_previous=True)
    assert [case["href"] for case in merged] == ["mapp", "weeks", "leon"]

def test_context_labels_holding_and_handles_missing_value():
    retriever = CaseRetriever()
    context = retriever.format_context_for_llm([
        {**CASES[0], "facts": "Police searched a home.", "question": "Was the evidence admissible?", "holding": "The exclusionary rule applies to the states."},
        {**CASES[1], "holding": ""},
    ])
    assert "Holding: The exclusionary rule applies to the states." in context
    assert "Holding: Not available in the supplied case record." in context
    assert "nan" not in context
    assert "None" not in context

def test_decision_summary_includes_split_and_justice_names():
    decisions = '[{"votes": [{"member": {"name": "Justice One"}, "vote": "majority"}, {"member": {"name": "Justice Two"}, "vote": "dissent"}]}]'
    summary = CaseRetriever._summarize_decisions(decisions)
    assert summary == {
        "vote_split": "1-1",
        "majority_justices": "Justice One",
        "minority_justices": "Justice Two",
    }

def test_decision_summary_includes_opinion_authors():
    decisions = '[{"votes": [{"member": {"name": "Justice Stewart"}, "vote": "majority", "opinion_type": "majority"}, {"member": {"name": "Justice White"}, "vote": "minority", "opinion_type": "dissent"}]}]'
    summary = CaseRetriever._summarize_decisions(decisions)
    assert summary["opinion_authors"] == "majority: Justice Stewart; dissent: Justice White"
    assert summary["majority_opinion_authors"] == "Justice Stewart"
    assert summary["dissent_authors"] == "Justice White"
```

### `tests/test_chat_navigation.py` — **Adapt** for NH case page routing.

### `tests/test_chat_providers.py` — **Copy verbatim**.

### `tests/test_chat_setup.py` — **Rewrite** with NH data paths.

---

## 11. Dependencies

**Core (always required):**
- streamlit
- pandas
- scikit-learn (TF-IDF vectorizer, cosine_similarity)
- python-dotenv (`.env` loading)
- requests (Gemini API calls)

**Optional (for hybrid retrieval upgrade):**
- pyarrow (Parquet I/O)
- sentence-transformers (dense embeddings)
- numpy (embedding operations)
- openai (OpenCode backup provider)

**Install:**
```bash
pip install streamlit pandas scikit-learn python-dotenv requests
# Optional:
pip install pyarrow sentence-transformers numpy openai
```

---

## 12. Environment Configuration

**File:** `.streamlit/secrets.toml` or `.env`

```toml
# Provider selection (default: gemini)
CHAT_PROVIDER = "gemini"

# Gemini API key (for default provider)
GEMINI_API_KEY = "your-gemini-api-key"

# OpenCode backup (alternative provider)
OPENCODE_API_KEY = "your-opencode-api-key"
```

**File:** `.env` (in repo root, loaded by `load_dotenv`)

```dotenv
CHAT_PROVIDER=gemini
GEMINI_API_KEY=...
```

The provider system follows this priority:
1. Environment variable `CHAT_PROVIDER` (for `.env`)
2. Streamlit secret `CHAT_PROVIDER` (for cloud deployment)
3. Default: `gemini`

**Important:** Never auto-fallback from Gemini to OpenCode — this prevents surprise API costs.

---

## Implementation Checklist for NH

- [ ] **Create `data/case_detail.parquet`** with NH case data (see §3)
- [ ] **Copy/adapt `utils/chat_retriever.py`** — update NH column names, paths, and source labels
- [ ] **Copy/adapt `utils/chat_formatter.py`** — update NH case page route
- [ ] **Copy `utils/chat_provider.py`** verbatim
- [ ] **Copy `utils/gemini_chat.py`** verbatim
- [ ] **Copy `utils/opencode_chat.py`** verbatim
- [ ] **Create/adapt `utils/text_search.py`** for NH data
- [ ] **Rewrite `pages/14_Chat.py`** — NH title, examples, source options, year range
- [ ] **Copy `utils/retrieval/`** files — adapt `service.py` paths, `metadata.py` field mapping
- [ ] **Copy tests** — adapt `test_chat_navigation.py` for NH routing
- [ ] **Update `CHAT_PROVIDERS.md`** and handoff docs
- [ ] **Verify** with the manual acceptance flow:
  1. Clear Chat, ask a topic question
  2. Confirm relevant sources
  3. Ask a follow-up (e.g., "What did the dissent say?")
  4. Confirm second retrieval stays anchored to prior cases
  5. Verify View buttons navigate to correct NH case page
  6. Confirm provider is the configured one
