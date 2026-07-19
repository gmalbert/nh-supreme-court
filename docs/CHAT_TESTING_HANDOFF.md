# Chat Implementation Testing — Handoff Document

**Date**: 2026-07-17
**Status**: ✅ Implementation complete, bugs fixed, ready for manual testing
**App URL**: http://localhost:8507 (may also be on 8504)

---

## Current State Summary

### ✅ What's Complete
- **48 files transferred** from supreme-court repo to nh-supreme-court
- **NH retrieval corpus built**: 2,801 cases in `data/retrieval/case_documents.parquet` (1.7 MB)
- **All modules compile** successfully with `py_compile`
- **All imports verified** working
- **Streamlit app running** on port 8507 (process confirmed)
- **Two critical bugs fixed** (see below)

### 🔧 Bugs Fixed Today

#### Bug 1: UnboundLocalError with `render_follow_ups`
**Error**: `UnboundLocalError: cannot access local variable 'render_follow_ups' where it is not associated with a value`

**Root Cause**: Chat module imports (`chat_retriever`, `chat_formatter`, `chat_provider`) were inside a conditional `try` block that only executed when search/ask buttons clicked. When Streamlit reran the script to display session state, the imports weren't available.

**Fix Applied**: Moved all chat imports to top of `cases.py` with other module imports (lines 60-72):
```python
# Chat module imports
from utils.chat_retriever import (
    build_retrieval_query,
    format_context,
    is_referential_followup,
    merge_retrieved_cases,
    retrieve_cases,
)
from utils.chat_formatter import format_with_links, render_sources, render_follow_ups
from utils.chat_provider import generate_chat_response
```

Removed duplicate imports from inside `_render_description_search()` function.

**Status**: ✅ Fixed, compiled successfully

#### Bug 2: StreamlitAPIException - Page Not Found
**Error**: `Could not find page: 'pages/1_Cases.py'`

**Root Cause**: Chat code from U.S. Supreme Court repo referenced `pages/1_Cases.py`, but NH app uses `pages/01_Opinions.py` as the case explorer page.

**Fix Applied**: Updated line 851 in `cases.py`:
```python
# OLD (from supreme-court repo):
st.switch_page("pages/1_Cases.py")

# NEW (for NH app):
st.switch_page("pages/01_Opinions.py")
```

**Status**: ✅ Fixed, compiled successfully

---

## Files Modified During Chat Implementation

### Core Files Modified
1. **cases.py** (main app entry point)
   - Added chat module imports (lines 60-72)
   - Replaced `_render_description_search()` function with Ask & Browse widget (lines ~697-942)
   - Added helper functions for hybrid retrieval (lines ~643-695)
   - Fixed: Removed duplicate imports from inside function
   - Fixed: Updated page reference to `pages/01_Opinions.py`

2. **requirements.txt**
   - Added: `python-dotenv>=1.0.0`
   - Added: `joblib>=1.5.0`
   - Added: `openai>=1.0.0`
   - Added: `pyarrow>=14.0.0`

3. **utils/text_search.py**
   - Modified to use NH corpus: `data/retrieval/case_documents.parquet`
   - Changed `_DETAIL_PARQUET` → `_CORPUS_PARQUET`
   - Updated `get_index()` to use `retrieval_text` field
   - Updated `is_available()` to check corpus parquet

4. **.env** (created)
   - Template with placeholder: `GEMINI_API_KEY=your-gemini-api-key-here`
   - User needs to add real API key for AI answers

### Files Added (48 total)

#### Chat Utilities (6 files)
- `utils/chat_retriever.py` — TF-IDF retrieval, referential detection, query building
- `utils/chat_formatter.py` — Response formatting, case links, source cards
- `utils/chat_provider.py` — LLM provider routing (Gemini/OpenCode)
- `utils/gemini_chat.py` — Gemini REST/SSE adapter
- `utils/opencode_chat.py` — OpenCode.ai GPT-4 adapter
- `utils/text_search.py` — TF-IDF search (modified for NH)

#### Retrieval Package (15 files in utils/retrieval/)
- `__init__.py`, `service.py`, `models.py`, `query_analyzer.py`
- `exact_index.py`, `lexical_index.py`, `dense_index.py`, `fusion.py`
- `metadata.py`, `context_builder.py`, `sufficiency.py`
- `transcript_index.py`, `diagnostics.py`, `normalize.py`, `legacy_adapter.py`

#### Build Scripts (5 files)
- `scripts/build_nh_retrieval_corpus.py` — ✅ Executed, corpus built
- `scripts/build_retrieval_corpus.py` — Original (not used for NH)
- `scripts/build_dense_index.py` — Optional semantic search
- `scripts/build_transcript_index.py` — Oral argument indexing
- `scripts/evaluate_retrieval.py` — Quality benchmarking

#### Test Suites (4 files)
- `tests/test_chat_conversation.py`
- `tests/test_chat_navigation.py`
- `tests/test_chat_providers.py`
- `tests/test_chat_setup.py`

#### Documentation (18 files)
- `docs/CHAT_IMPLEMENTATION_COMPLETE.md`
- `docs/CHAT_TESTING_GUIDE.md`
- `docs/CHAT_IMPLEMENTATION_FINAL_SUMMARY.md`
- `docs/CHAT_MANUAL_TEST_CHECKLIST.md`
- `docs/CHAT_INTEGRATION_PLAN.md`
- `docs/CHAT_IMPLEMENTATION_HANDOFF.md`
- `docs/CHAT_PROVIDERS.md`
- `docs/CHAT_CONVERSATION_HANDOFF.md`
- Plus 10 more chat-related docs from supreme-court repo

#### Config Files (2 files)
- `.env` — API key configuration
- `.streamlit/secrets.toml.example` — Alternative config template

---

## Ask & Browse Widget — Technical Details

### Location
`cases.py` → `render_dashboard()` → `_render_description_search(df)` (lines ~697-942)

### UI Components
```
┌─────────────────────────────────────────────────────┐
│ 💬 Ask & Browse                                      │
│ ┌─────────────────────────────────────────────────┐ │
│ │ text_area: "e.g. What are the landmark cases..." │ │
│ └─────────────────────────────────────────────────┘ │
│                                                       │
│ [Results: 3━━━━○━━━━20] [🔍 Search] [🚀 Ask AI]     │
│                                                       │
│ ─────────────────────────────────────────────────── │
│ 💬 AI Answer (if Ask AI clicked)                    │
│   - Streaming markdown response                      │
│   - Follow-up question buttons (3 suggestions)       │
│   - 📚 Sources (N cases) expander                    │
│                                                       │
│ ─────────────────────────────────────────────────── │
│ 📚 Search Results                                    │
│ ┌───────────────┬─────────────────────────────────┐ │
│ │ Case List     │ Case Detail Panel               │ │
│ │ (left column) │ (right column, click to view)   │ │
│ └───────────────┴─────────────────────────────────┘ │
└─────────────────────────────────────────────────────┘
```

### Session State Variables
- `ask_query` — Current query text
- `ask_results` — Retrieved cases (list of dicts)
- `ask_selected_case` — Currently selected case in detail panel
- `ask_previous_query` — Last query (for referential follow-ups)
- `ask_previous_cases` — Last results (for context)
- `ask_answer` — AI response text (formatted markdown)
- `ask_previous_answer` — Last AI response (for conversation history)
- `ask_follow_ups` — List of 3 follow-up question suggestions
- `_pending_followup_query` — Queued follow-up (triggers rerun)
- `_auto_ask` — Flag to auto-trigger AI answer after follow-up

### Retrieval Flow

#### 🔍 Search Button (Simple Search)
1. User enters query → clicks "🔍 Search"
2. `retrieve_cases(query, "nh-supreme-court", top_k=N)`
3. Uses `utils/text_search.py` → TF-IDF on `retrieval_text` field
4. Returns list of case dicts with `name`, `href`, `score`, etc.
5. Display results in 2-column layout (list + detail)
6. **No LLM call** (works without API key)

#### 🚀 Ask AI Button (Retrieval + LLM)
1. User enters query → clicks "🚀 Ask AI"
2. Check if referential follow-up: `is_referential_followup(query)`
3. Build enhanced query: `build_retrieval_query(query, prev_query, prev_cases)`
4. Attempt hybrid retrieval: `_try_hybrid_retrieval()` (optional)
   - Falls back to TF-IDF if hybrid unavailable
5. Merge with previous cases: `merge_retrieved_cases(fresh, prior, ...)`
6. Format context for LLM: `format_context(cases)`
7. Call LLM: `generate_chat_response(query, context, history, stream=True)`
8. Stream response chunks → format with case links
9. Generate follow-up questions: `_ask_generate_follow_ups(cases)`
10. Display: AI answer + follow-ups + sources + results

### Data Schema

#### NH Retrieval Corpus Fields
File: `data/retrieval/case_documents.parquet` (2,801 rows)

| Field | Source | Example |
|---|---|---|
| `case_id` | Generated SHA-256 | `f8a3c9d2...` |
| `name` | `case_name` | `State v. Smith` |
| `normalized_name` | Normalized | `state v smith` |
| `href` | `case_number` | `2023-0123` |
| `term` | `term_year` | `2023` |
| `docket_number` | `docket_numbers` | `2023-0123` |
| `citation` | `citation` | `175 N.H. 456` |
| `facts` | `summary_paragraph` | `On appeal from...` |
| `question` | Generated | `Appeal from Superior Court` |
| `holding` | `outcome` | `Affirmed` |
| `retrieval_text` | Combined fields | `name: ... summary: ...` |

#### Legacy Case Dict Format (from retrieval)
```python
{
    "name": "State v. Smith",
    "term": "2023",
    "href": "2023-0123",
    "docket_number": "2023-0123",
    "citation": "175 N.H. 456",
    "facts": "On appeal from...",
    "holding": "Affirmed",
    "score": 2.456,
    "case_number": "2023-0123",  # Added for NH compatibility
}
```

---

## Testing Status

### ✅ Automated Tests Passed
- `py_compile` all 48 files: ✅ All compile
- Module imports: ✅ All working
- Corpus build: ✅ 2,801 cases
- TF-IDF search: ✅ Verified ("search warrant" → 3 results)
- Streamlit startup: ✅ Running on port 8507

### 🔄 Manual Testing Needed

**Test without API key** (priority):
1. Open http://localhost:8507
2. Scroll to "💬 Ask & Browse" widget
3. Enter: `search warrant exceptions`
4. Click "🔍 Search" (NOT Ask AI)
5. **Expected**: 8-10 results appear, case list clickable, detail panel works
6. Click "Open Case →" button
7. **Expected**: Navigates to Opinions page with case highlighted

**Test with API key** (requires setup):
1. Get Gemini API key from https://aistudio.google.com/app/apikey
2. Add to `.env`: `GEMINI_API_KEY=your-actual-key`
3. Restart Streamlit: `pkill -f "streamlit run cases.py" && source venv_mac/bin/activate && streamlit run cases.py --server.port 8507`
4. Enter: `When can police search a car without a warrant?`
5. Click "🚀 Ask AI"
6. **Expected**:
   - "Thinking..." spinner appears
   - AI answer streams in (mentions automobile exception, probable cause, NH cases)
   - 3 follow-up buttons appear
   - Sources expander shows case cards
7. Click a follow-up button
8. **Expected**: Query auto-fills, AI generates new answer with context

**Edge cases** (see CHAT_MANUAL_TEST_CHECKLIST.md for full list):
- Empty query
- No results query
- Very long query
- Missing API key error

---

## Known Issues & Limitations

### ✅ Fixed
- ~~`render_follow_ups` UnboundLocalError~~ → Fixed by moving imports to top
- ~~`pages/1_Cases.py` not found~~ → Fixed by updating to `pages/01_Opinions.py`

### ⚠️ Potential Issues (Not Yet Tested)
1. **Hybrid retrieval not built** — App uses TF-IDF fallback only
   - Dense embeddings index doesn't exist yet
   - To build: `python scripts/build_dense_index.py` (requires sentence-transformers)
2. **API key placeholder** — User must configure real key
3. **Conversation history** — May accumulate in session state, no clear button yet
4. **Mobile responsiveness** — Not tested on mobile browsers
5. **Performance** — TF-IDF index builds on first search (~1-2 sec delay)

### 🔮 Future Enhancements
- Add "Clear conversation" button
- Add legal disclaimer to AI answers
- Export conversation to CSV/JSON
- Integrate oral argument transcripts
- Add user feedback buttons (👍/👎)
- Fine-tune embedding model on NH legal text

---

## Environment Setup

### Python Environment
```bash
source venv_mac/bin/activate  # Activate virtual environment
python --version              # 3.9+
```

### Dependencies Installed
```
streamlit>=1.36.0
pandas>=2.0.0
plotly>=5.18.0
scikit-learn>=1.3.0
python-dotenv==1.2.2
joblib>=1.5.0
openai==2.46.0
pyarrow>=14.0.0
```

### Streamlit App Management
```bash
# Check if running
ps aux | grep "streamlit run cases.py" | grep -v grep

# Start app
source venv_mac/bin/activate
streamlit run cases.py --server.port 8507

# Stop app
pkill -f "streamlit run cases.py"

# Restart app (after .env changes)
pkill -f "streamlit run cases.py"
source venv_mac/bin/activate
streamlit run cases.py --server.port 8507
```

### Configuration Files
```bash
# .env file (API keys)
GEMINI_API_KEY=your-gemini-api-key-here
# OPENCODE_API_KEY=optional-backup-provider

# Alternative: .streamlit/secrets.toml
[chat]
GEMINI_API_KEY = "your-key-here"
```

---

## Quick Debugging Guide

### App Won't Start
```bash
# Check Python environment
which python
# Should be: /Volumes/Users/gmalb/Downloads/nh-supreme-court/venv_mac/bin/python

# Verify dependencies
pip list | grep -E "(streamlit|pandas|dotenv)"

# Check for port conflicts
lsof -i :8507
```

### Import Errors
```bash
# Test chat modules manually
python -c "from utils.chat_retriever import retrieve_cases"
python -c "from utils.chat_formatter import format_with_links"
python -c "from utils.chat_provider import generate_chat_response"
python -c "from utils.text_search import search, is_available"
```

### Retrieval Issues
```bash
# Verify corpus exists
ls -lh data/retrieval/case_documents.parquet
# Expected: 1.7 MB file

# Test TF-IDF search
python -c "
from utils.text_search import search
results = search('search warrant', top_k=3)
print(f'{len(results)} results')
for r in results:
    print(f'  {r[\"name\"][:50]}... score={r[\"score\"]:.3f}')
"
```

### API Key Issues
```bash
# Check .env file exists
cat .env

# Verify key loaded (in Python)
python -c "
import os
from dotenv import load_dotenv
load_dotenv()
key = os.getenv('GEMINI_API_KEY')
print(f'Key loaded: {key[:10]}...' if key else 'No key found')
"
```

### Browser DevTools
1. Open browser console (F12)
2. Look for errors in Console tab
3. Check Network tab for failed API requests
4. Hard refresh: Cmd+Shift+R (Mac) or Ctrl+Shift+R (Windows)

---

## Next Steps (Priority Order)

### Immediate (Testing)
1. ✅ **Fix bugs** (DONE: imports, page reference)
2. 🔄 **Manual browser test** — Search button functionality
3. 🔄 **Configure API key** — Get Gemini key, add to .env
4. 🔄 **Test AI answers** — Full flow with LLM
5. 🔄 **Test follow-ups** — Multi-turn conversation

### Short Term (Enhancements)
- Add legal disclaimer to AI answers
- Add "Clear conversation" button
- Test edge cases (empty query, no results, etc.)
- Run pytest tests: `pytest tests/test_chat_*.py`
- Document any UX improvements needed

### Medium Term (Optional Features)
- Build dense embeddings: `python scripts/build_dense_index.py`
- Integrate oral argument transcripts (NH-specific adaptation)
- Export conversation feature
- Mobile testing and optimization

### Long Term (Advanced)
- Fine-tune embedding model on NH legal text
- Add citation network traversal
- Build statutory cross-reference index (RSA)
- Implement case law knowledge graph

---

## Key Files Reference

### Documentation (Read These First)
1. `docs/CHAT_IMPLEMENTATION_COMPLETE.md` — Full technical overview
2. `docs/CHAT_TESTING_GUIDE.md` — Testing scenarios
3. `docs/CHAT_MANUAL_TEST_CHECKLIST.md` — Step-by-step test plan
4. `docs/CHAT_IMPLEMENTATION_FINAL_SUMMARY.md` — Verification results
5. **This file** — Testing handoff

### Code Entry Points
- `cases.py` line 697 → `_render_description_search()` — Ask & Browse widget
- `utils/chat_retriever.py` → `retrieve_cases()` — Main retrieval function
- `utils/chat_provider.py` → `generate_chat_response()` — LLM routing
- `utils/text_search.py` → `search()` — TF-IDF search
- `scripts/build_nh_retrieval_corpus.py` — Corpus builder (already run)

### Data Files
- `data/retrieval/case_documents.parquet` — 2,801 NH cases (1.7 MB)
- `data/processed/opinions.csv` — Source data (2,801 opinions)
- `.env` — API key configuration (needs real key)

---

## Testing Handoff Summary

**Current Task**: Manual browser testing of Ask & Browse widget

**What's Ready**:
✅ All files compiled
✅ All modules imported
✅ Bugs fixed
✅ App running on http://localhost:8507
✅ Retrieval corpus built (2,801 cases)

**What's Needed**:
1. Open http://localhost:8507 in browser
2. Test 🔍 Search button (no API key needed)
3. Get Gemini API key from https://aistudio.google.com/app/apikey
4. Add to `.env` file: `GEMINI_API_KEY=your-key`
5. Restart Streamlit
6. Test 🚀 Ask AI button (full LLM integration)

**Success Criteria**:
- Search returns relevant NH cases
- Case detail viewer displays correctly
- "Open Case →" navigates to Opinions page
- AI answers cite retrieved cases
- Follow-up questions work
- No errors in browser console

**If Bugs Found**:
1. Check browser console (F12) for errors
2. Check Streamlit terminal for stack traces
3. Verify `.env` file has real API key
4. Verify retrieval corpus exists (1.7 MB parquet)
5. Check `docs/CHAT_TESTING_GUIDE.md` troubleshooting section

---

**Ready to test!** Start at: http://localhost:8507 🚀

**Questions?** Check the comprehensive docs in `docs/CHAT_*.md` files.
