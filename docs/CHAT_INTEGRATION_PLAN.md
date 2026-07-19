# Chat Integration Plan — Merge Chat into the Home Page

**Date:** 2026-07-07
**Goal:** Eliminate the standalone Chat page (`pages/14_Chat.py`) by integrating the chat assistant directly into the home page (`cases.py`), replacing the old "Find Cases by Description" redirect and removing the redundant "Explore the Court" nav cards.

---

## Rationale for home page placement

The original plan targeted the Cases page's "Find by Description" tab. During implementation, the home page was chosen instead because:

1. **The old home page widget was a dead end** — it took a query then `st.switch_page` to Cases. No actual search happened on the home page.
2. **Removing the nav cards** freed enough vertical space for the AI widget, and those cards were redundant with the sidebar.
3. **One fewer click** — users land, ask, get results + AI answer immediately.

## What changed

| Before | After |
|---|---|
| `cases.py` had a text box + button that redirected to Cases | `cases.py` has the full Ask & Browse widget inline |
| `cases.py` had "Explore the Court" nav cards (sidebar duplicates) | Nav cards removed |
| `pages/14_Chat.py` existed with full chat UI | `14_Chat.py` deleted |
| Sidebar had "Chat Assistant" nav entry | Sidebar entry removed |
| `1_Cases.py` had `_chat_nav_*` session key handlers | Dead code removed |

## Home page layout (top to bottom)

```
Hero (logo + title)
On This Day in SCOTUS History
─────────────────────────────────────────
💬 Ask & Browse  (border container)
  ┌─ text_area (height=80) ─────────────────┐
  │ "e.g. police searched a suspect's..."   │
  └─────────────────────────────────────────┘
  [8 results ▬▬▬○▬▬▬]  [🔍 Search]  [🚀 Ask AI]
  ─────────────────────────────────────────
  💬 AI Answer  ← shown only when Ask AI clicked
  ┌─────────────────────────────────────────┐
  │  Streaming markdown response...          │
  │  Follow-up buttons                       │
  │  📚 Sources (N cases) ▸ (expander)       │
  └─────────────────────────────────────────┘
  📚 Search Results (always shown)
  ┌── list ─────────┐ ┌── detail ──────────┐
  │ 1. Mapp v. Ohio │ │ (click to view)    │
  │ 2. Weeks v. US  │ │                    │
  └──────────────────┘ └────────────────────┘
─────────────────────────────────────────
ℹ️ About Supreme Scrutiny (expander)
```

### How the two buttons work

| Button | Search runs | LLM runs | Results shown | Follow-ups |
|---|---|---|---|---|
| 🔍 Search | Yes | No | Updated | Hidden, prior context cleared |
| 🚀 Ask AI | Yes | Yes | Updated | Generated from results |

## Multi-turn flow

1. User asks "What are the major exclusionary-rule cases?" → clicks Ask AI
2. TF-IDF (or hybrid) runs → results appear in list + AI answer streams below
3. Follow-up buttons appear under the answer
4. User clicks "Compare the reasoning in Mapp v. Ohio and United States v. Leon"
5. Query box fills with that text → rerun triggers automatically
6. `is_referential_followup` detects referential patterns
7. `build_retrieval_query` appends prior cases to the search query
8. `merge_retrieved_cases` deduplicates prior + fresh results
9. New answer streams in, new follow-ups appear

```
┌─────────────────────────────────────────────────────┐
│  Ask a question or describe a legal situation        │
│  ┌─────────────────────────────────────────────────┐│
│  │ text_area, height=80                            ││
│  │ placeholder: "e.g. What are the major           ││
│  │ exclusionary-rule cases?"                       ││
│  └─────────────────────────────────────────────────┘│
│  [8 results ▬▬▬○▬▬▬]  [🔍 Search]  [🚀 Ask AI]     │
├─────────────────────────────────────────────────────┤
│  💬 AI Answer  ← shown only when user clicks Ask AI  │
│  ┌─────────────────────────────────────────────────┐│
│  │  Streaming markdown response...                  ││
│  │                                                  ││
│  │  💡 Follow-up Questions                          ││
│  │  ┌──────────────────┐ ┌──────────────────┐       ││
│  │  │ What were the    │ │ Compare the      │       ││
│  │  │ key facts in     │ │ reasoning in     │       ││
│  │  │ Mapp v. Ohio?    │ │ Mapp and Leon.   │       ││
│  │  └──────────────────┘ └──────────────────┘       ││
│  │  📚 Sources (5 cases) ▸ (expander)               ││
│  └─────────────────────────────────────────────────┘│
├─────────────────────────────────────────────────────┤
│  📚 Search Results  ← always shown (same as now)     │
│  ┌────────── list ──────────┐ ┌── detail ─────────┐│
│  │ 1. Mapp v. Ohio         │ │                    ││
│  │   1971 term · score 0.87 │ │  (click to view)  ││
│  │ 2. Weeks v. US          │ │                    ││
│  │ 3. United States v. Leon │ │                    ││
│  └──────────────────────────┘ └────────────────────┘│
└─────────────────────────────────────────────────────┘
```

### How the two buttons work

| Button | Search runs | LLM runs | Results shown | Follow-ups |
|---|---|---|---|---|
| 🔍 Search | Yes | No | Updated | Hidden, prior context cleared |
| 🚀 Ask AI | Yes | Yes | Updated | Generated from results |

Both buttons share the same retrieval. The only difference is whether an LLM answer is generated on top.

### Multi-turn flow

1. User asks "What are the major exclusionary-rule cases?" → clicks Ask AI
2. TF-IDF runs → results appear in list + AI answer streams in below
3. Follow-up buttons appear under the answer
4. User clicks "How does United States v. Leon limit Mapp v. Ohio?"
5. Query box fills with that text → rerun triggers automatically
6. `is_referential_followup` detects the referential patterns
7. `build_retrieval_query` appends prior cases to the search query
8. `merge_retrieved_cases` deduplicates prior + fresh results
9. New answer streams in, new follow-ups appear

## Files changed

### 1. `cases.py` — the main work

**Added (top-level imports):**
- `dotenv`, `chat_formatter` utilities, `text_search`, `typing.List/Dict`

**Added (helper functions):**
- `_hybrid_retrieval_available()` — checks for hybrid retrieval artifacts
- `_retrieve_via_hybrid()` — calls the `RetrievalService` and returns legacy-shaped case dicts
- `_try_hybrid_retrieval()` — wrapper that populates a diagnostics dict as side effect
- `_ask_generate_follow_ups()` — generates local follow-up questions from retrieved case names

**Replaced:**
- The old "🔍 Find Cases by Description" section (which was just a redirect to Cases) with the full Ask & Browse widget (AI-powered search with results + optional AI answer + follow-ups + case detail panel)

**Removed:**
- The "Explore the Court" navigation card section (4 cards linking to Cases, People, Predictions, Analytics — all redundant with sidebar navigation)
- The `st.Page("pages/14_Chat.py", ...)` entry from the sidebar navigation dict

### 2. `pages/1_Cases.py` — dead code cleanup

**Removed:**
- `_chat_nav_q` / `_chat_nav_case` session state handlers (lines 98–101)
- `_chat_selected_case` fallback in the search selectbox (line 122)

### 3. `pages/14_Chat.py` — deleted

The standalone chat page is no longer needed. Its functionality lives on the home page with more context and fewer clicks.

### 4. `tests/test_chat_setup.py` — updated

Replaced `test_page_exists()` (checked for `14_Chat.py`) with `test_home_page_chat()` (verifies the Ask & Browse widget exists in `cases.py`).

---

## Session state keys

| Old (14_Chat.py) | New (cases.py home_page) | Purpose |
|---|---|---|
| `chat_messages` | `ask_previous_query`, `ask_previous_answer`, `ask_previous_cases` | Multi-turn history (simplified — no full message log) |
| `chat_query_count` | — removed — | Rate limit not needed on home page |
| `chat_source` | reuses existing | Source selector if multi-source |
| `pending_question` | `ask_query` | Pre-fill from follow-up click |
| `chat_num_cases` | `ask_n` (slider) | Results count |

---

## Migration checklist

- [x] Add `ask_query`, `ask_results`, `ask_n` session keys
- [x] Replace home page "Find Cases by Description" with Ask & Browse widget
- [x] Add `_ask_generate_follow_ups()` helper function
- [x] Add `_hybrid_retrieval_available()`, `_retrieve_via_hybrid()`, `_try_hybrid_retrieval()`
- [x] Test: plain search still works (🔍 Search button)
- [x] Test: Ask AI streams an answer with linked case citations
- [x] Test: follow-up buttons appear and pre-fill query on click
- [x] Test: referential follow-up expands query with prior context
- [x] Test: prior and fresh results deduplicate correctly
- [x] Test: clicking a result loads detail panel
- [x] Test: no leftover `14_Chat.py` dependencies
- [x] Remove `_chat_nav_*` dead code from `1_Cases.py`
- [x] Remove `pages/14_Chat.py`
- [x] Remove Chat from navigation config in `cases.py`
- [x] Update `tests/test_chat_setup.py`
- [x] Remove "Explore the Court" nav cards from home page

---

## Open questions (resolved during implementation)

1. **Conversation history depth** — Only the immediate prior query/answer/cases is stored. One exchange back is sufficient for referential follow-ups. Deeper history can be added later if needed.

2. **Rate limit** — Removed. The home page context doesn't need it.

3. **AI vs Search buttons** — Two-button approach (🔍 Search / 🚀 Ask AI) is implemented. Pure search clears AI context.

4. **Sources expander** — Collapsed by default under "📚 Sources (N cases)".

5. **No tab needed** — Since the widget is on the home page, there's no tab label question. The heading is "💬 Ask & Browse".
