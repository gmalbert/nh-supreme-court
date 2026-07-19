# Chat Implementation Testing Guide

**App URL**: http://localhost:8507
**Status**: ✅ App running, retrieval corpus built, ready to test

---

## Quick Test Checklist

### ✅ **Already Complete**
- [x] Chat modules copied (6 utilities + 15 retrieval modules)
- [x] Cases.py updated with Ask & Browse widget
- [x] Requirements.txt updated with dependencies
- [x] All 43 files compile successfully
- [x] Retrieval corpus built (2,801 NH cases)
- [x] .env template created
- [x] Streamlit app running on http://localhost:8507

### 🧪 **Test Scenarios**

#### Test 1: Simple Search (No API Key Required)
1. Navigate to http://localhost:8507
2. Find the **💬 Ask & Browse** widget on the home page
3. Type a query: `police search without warrant`
4. Click **🔍 Search** button
5. **Expected**: Search results appear in 2-column layout
   - Left: Case list with rank, name, term, score
   - Right: "← Select a case to read it" placeholder
6. Click **View →** on any case
7. **Expected**: Case details appear in right panel

#### Test 2: Case Detail Viewer
1. After clicking View → on a case:
2. **Expected**:
   - Case name as header
   - Metadata (term, case number, outcome)
   - Expandable sections:
     - 📋 Facts (if available)
     - ❓ Legal Question (if available)
     - ⚖️ Holding (if available)

#### Test 3: Open Case Navigation
1. Click **Open Case →** button on any result
2. **Expected**: Navigate to Case Explorer page with that case pre-selected

#### Test 4: AI-Powered Answer (Requires API Key)
**Setup**: Configure GEMINI_API_KEY in `.env` file

1. Type a question: `What are the major search and seizure cases?`
2. Click **🚀 Ask AI** button
3. **Expected**:
   - Spinner: "🔍 Searching cases..."
   - AI answer streams in below query box
   - Follow-up question buttons appear (3 suggestions)
   - Sources expander shows case cards
   - Search results appear below

#### Test 5: Follow-Up Questions
1. After getting an AI answer, click a follow-up button
2. **Expected**:
   - Query box fills with follow-up text
   - App reruns automatically
   - New answer generated with prior context

#### Test 6: Fallback Behavior
1. Test with GEMINI_API_KEY **not** configured
2. Click **🚀 Ask AI** button
3. **Expected**: Either:
   - Error message: "⚠️ AI error: ..."
   - Fallback to simple search results

---

## Known Issues to Check

### Issue 1: "Chat modules not available" error
**Symptom**: Error when clicking Search or Ask AI
**Cause**: Import failure in chat modules
**Debug**:
```bash
python -c "from utils.chat_retriever import retrieve_cases; print('✓ OK')"
python -c "from utils.chat_formatter import format_with_links; print('✓ OK')"
python -c "from utils.chat_provider import generate_chat_response; print('✓ OK')"
```

### Issue 2: "No matching cases found" for all queries
**Symptom**: Empty results for any query
**Cause**: Retrieval corpus not loaded or index build failed
**Debug**:
```bash
# Check corpus exists
ls -lh data/retrieval/case_documents.parquet

# Test TF-IDF index build
python -c "from utils.text_search import is_available; print(is_available())"
```

### Issue 3: Field mapping errors
**Symptom**: Case details show "Unknown" or missing data
**Cause**: NH data fields don't match expected retrieval schema
**Debug**: Check console for KeyError or AttributeError
**Fix**: Update field mappings in `build_nh_retrieval_corpus.py`

---

## Manual Verification Steps

### 1. Check Retrieval Corpus
```bash
python -c "
import pandas as pd
df = pd.read_parquet('data/retrieval/case_documents.parquet')
print(f'Cases: {len(df):,}')
print(f'Columns: {list(df.columns)}')
print(f'Sample:\n{df.iloc[0][\"name\"]}\n{df.iloc[0][\"retrieval_text\"][:200]}...')
"
```

**Expected output**:
```
Cases: 2,801
Columns: ['case_id', 'name', 'normalized_name', 'href', 'term', ...]
Sample:
LD-97-009, FELD'S CASE
name: LD-97-009, FELD'S CASE
summary: On June 19, 1997, the Supreme Court...
```

### 2. Test TF-IDF Search
```bash
python -c "
from utils.text_search import search
results = search('search warrant', top_k=5)
print(f'Found {len(results)} results')
for r in results[:3]:
    print(f'  - {r[\"name\"]} (score: {r[\"score\"]:.3f})')
"
```

**Expected**: 5 results with scores ~0.1-0.5

### 3. Test Chat Retriever
```bash
python -c "
from utils.chat_retriever import retrieve_cases
results = retrieve_cases('police search', source='nh-supreme-court', top_k=5)
print(f'Retrieved {len(results)} cases')
for r in results[:2]:
    print(f'  - {r.get(\"name\", \"Unknown\")}')
"
```

**Expected**: 5 case dicts with name, term, score, etc.

### 4. Test Provider (Without Streaming)
```bash
# Only if GEMINI_API_KEY configured
python -c "
from utils.chat_provider import generate_chat_response
response = generate_chat_response(
    user_message='What is a search warrant?',
    case_context='',
    conversation_history=[],
    stream=False
)
print(response[:200] + '...')
"
```

**Expected**: Text response from Gemini (or error if no API key)

---

## Browser DevTools Debugging

### Check Network Requests
1. Open browser DevTools (F12)
2. Go to Network tab
3. Click Ask AI button
4. Look for:
   - `/component/st.text_area` (query input update)
   - `/script-run-request` (Streamlit rerun)
   - Any failed requests (red)

### Check Console Errors
1. Open Console tab
2. Click Search or Ask AI
3. Look for:
   - JavaScript errors (red)
   - React errors
   - WebSocket errors

### Check Session State
1. Install Streamlit session state viewer (if available)
2. Or add debug output:
```python
# In cases.py, add temporarily:
st.write("Session State:", st.session_state)
```

---

## Performance Benchmarks

### Expected Response Times

| Action | Expected Time | Notes |
|---|---|---|
| First search (cold start) | 2-5s | Index build + search |
| Subsequent searches | 200-500ms | Cached index |
| AI answer (first token) | 500-1000ms | API latency |
| AI answer (complete) | 3-6s | Streaming |
| Follow-up question | 1-2s | Cached context |

### Memory Usage

| Component | Expected Size |
|---|---|
| TF-IDF vectorizer | ~5-10 MB |
| TF-IDF matrix (2,801 cases) | ~10-20 MB |
| Retrieval corpus | 1.7 MB |
| Session state (per user) | ~1-2 MB |

---

## Troubleshooting Commands

### Reset session state
Navigate to: http://localhost:8507/?reset_session=1

### Clear Streamlit cache
```bash
# Delete cache directory
rm -rf .streamlit/cache/

# Or restart app
pkill -f "streamlit run cases.py"
source venv_mac/bin/activate
streamlit run cases.py --server.port 8507
```

### Rebuild retrieval corpus
```bash
python scripts/build_nh_retrieval_corpus.py
```

### Check logs
```bash
# Streamlit logs in terminal
# Look for Python tracebacks, import errors, etc.
```

---

## Success Criteria

✅ **Basic Search Works**
- [ ] Query box accepts input
- [ ] Search button returns results
- [ ] Results show case name, term, score
- [ ] Clicking View → shows case details
- [ ] Open Case → navigates to Case Explorer

✅ **AI Answer Works** (with API key)
- [ ] Ask AI button triggers LLM
- [ ] Answer streams in below query
- [ ] Case names auto-linked
- [ ] Follow-up buttons appear
- [ ] Sources expander shows cases

✅ **Multi-Turn Works**
- [ ] Follow-up button fills query
- [ ] App reruns automatically
- [ ] Prior cases included in context
- [ ] New answer references old context

✅ **Error Handling**
- [ ] No API key → graceful error or fallback
- [ ] Empty query → no crash
- [ ] No results → helpful message
- [ ] Import errors → fallback to simple search

---

## Next Steps After Testing

### If Tests Pass ✅
1. Mark chat integration as complete
2. Update main README with chat features
3. Create user-facing documentation
4. Consider building dense index for semantic search
5. Add legal disclaimer to AI answers

### If Tests Fail ❌
1. Check terminal for Python tracebacks
2. Verify dependencies installed: `pip install -r requirements.txt`
3. Check retrieval corpus: `ls -lh data/retrieval/`
4. Test individual modules with debug commands above
5. Review browser console for JS errors
6. Check field mappings in `build_nh_retrieval_corpus.py`

---

## Contact & Support

**Documentation**:
- [CHAT_IMPLEMENTATION_COMPLETE.md](CHAT_IMPLEMENTATION_COMPLETE.md) — Full technical overview
- [CHAT_INTEGRATION_PLAN.md](CHAT_INTEGRATION_PLAN.md) — Integration strategy
- [CHAT_IMPLEMENTATION_HANDOFF.md](CHAT_IMPLEMENTATION_HANDOFF.md) — Detailed handoff guide

**Debugging**:
- Check `utils/text_search.py` for TF-IDF index issues
- Check `utils/chat_retriever.py` for retrieval logic
- Check `cases.py` for UI integration
- Check `scripts/build_nh_retrieval_corpus.py` for data mapping

**Common Fixes**:
- Install missing deps: `pip install python-dotenv joblib openai pyarrow`
- Rebuild corpus: `python scripts/build_nh_retrieval_corpus.py`
- Clear cache: `rm -rf .streamlit/cache/`
- Restart app: `streamlit run cases.py --server.port 8507`
