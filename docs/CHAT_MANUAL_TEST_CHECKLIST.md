# Chat Widget — Manual Testing Checklist

**Date**: 2026-07-17
**App URL**: http://localhost:8507
**Status**: ✅ All components ready

---

## Pre-Test Verification ✅

- ✅ **App running**: Process 45055 on port 8507
- ✅ **Retrieval corpus**: 2,801 cases (1.7 MB parquet)
- ✅ **.env file exists**: API key configuration ready
- ✅ **TF-IDF search**: Verified working (3 results for "search warrant")

---

## Test Scenario 1: Basic Search (No API Key Required)

**Purpose**: Verify retrieval works without LLM

### Steps:
1. Open http://localhost:8507 in browser
2. Scroll to **💬 Ask & Browse** widget
3. Enter query: `search warrant exceptions`
4. Adjust results slider to **10**
5. Click **🔍 Search** button (NOT "Ask AI")

### Expected Results:
- ✅ **Results appear** within 2-3 seconds
- ✅ **Case list** shows ~10 cases in left column
- ✅ **Case names** are links (e.g., "In re Search Warrant...")
- ✅ **Relevance scores** shown (e.g., "Score: 2.03")
- ✅ **No AI answer section** (only search results)
- ✅ **Detail panel** on right shows placeholder "Select a case..."

### Test Result: ☐ Pass / ☐ Fail

**Notes**:
```
[Your observations here]
```

---

## Test Scenario 2: Case Detail Viewer

**Purpose**: Verify case detail panel works

### Steps:
1. From Test Scenario 1, click **first case** in results list
2. Observe detail panel on right

### Expected Results:
- ✅ **Case name** appears as heading
- ✅ **Metadata** shows: Docket, Term, Citation
- ✅ **Summary** paragraph displays
- ✅ **Outcome** shows (e.g., "Affirmed")
- ✅ **"Open Case →" button** appears at bottom

### Test Result: ☐ Pass / ☐ Fail

**Notes**:
```
[Your observations here]
```

---

## Test Scenario 3: Navigation to Case Explorer

**Purpose**: Verify "Open Case →" button works

### Steps:
1. From Test Scenario 2, click **"Open Case →"** button
2. Observe page navigation

### Expected Results:
- ✅ **Navigates** to "Opinions" page (pages/01_Opinions.py)
- ✅ **Case highlighted** in Opinions table
- ✅ **Filters applied** to show selected case

### Test Result: ☐ Pass / ☐ Fail

**Notes**:
```
[Your observations here]
```

---

## Test Scenario 4: Configure API Key

**Purpose**: Set up Gemini API for AI answers

### Steps:
1. Open `.env` file in editor
2. Replace `your-gemini-api-key-here` with real API key
3. Save file
4. **Restart Streamlit app**:
   ```bash
   # In terminal where Streamlit is running:
   Ctrl+C  # Stop app
   source venv_mac/bin/activate && streamlit run cases.py --server.port 8507
   ```
5. Refresh browser at http://localhost:8507

### Expected Results:
- ✅ **App restarts** without errors
- ✅ **API key loaded** (check terminal for warnings)

### Test Result: ☐ Pass / ☐ Fail

**Notes**:
```
API Key (last 4 chars): ____
```

---

## Test Scenario 5: AI Answer (Requires API Key)

**Purpose**: Verify LLM integration works

### Steps:
1. Ensure API key configured (Test Scenario 4)
2. Enter query: `When can police search a car without a warrant?`
3. Click **🚀 Ask AI** button
4. Wait for response

### Expected Results:
- ✅ **"Thinking..." spinner** appears
- ✅ **AI Answer section** appears with markdown text
- ✅ **Streaming response** (text appears gradually)
- ✅ **Case names italicized** and linked (e.g., *State v. Smith*)
- ✅ **Follow-up buttons** appear (3 suggestions)
- ✅ **"📚 Sources (N cases)" expander** appears
- ✅ **Search results** still visible below

### Expected Answer Content:
- Should mention **automobile exception** to warrant requirement
- Should cite **NH cases** (not just general law)
- Should reference **probable cause** requirement
- Should use cases from retrieval results

### Test Result: ☐ Pass / ☐ Fail

**Notes**:
```
[Response quality notes]
```

---

## Test Scenario 6: Follow-Up Questions

**Purpose**: Verify multi-turn conversation works

### Steps:
1. From Test Scenario 5, click one of the **follow-up buttons**
2. Observe behavior

### Expected Results:
- ✅ **Query box auto-fills** with follow-up question
- ✅ **🚀 Ask AI triggers automatically** (or requires click)
- ✅ **New answer appears** above old answer (or replaces it)
- ✅ **Prior cases included** in context (referential follow-up detection)
- ✅ **New sources** shown in expander

### Test Result: ☐ Pass / ☐ Fail

**Notes**:
```
[Your observations here]
```

---

## Test Scenario 7: Source Cards

**Purpose**: Verify case source display

### Steps:
1. From Test Scenario 5, expand **"📚 Sources (N cases)"**
2. Observe case cards

### Expected Results:
- ✅ **Each case** has card with:
  - Case name (bold)
  - Term year
  - Docket number
  - Citation
  - Relevance score
  - "View" button
- ✅ **"View" button** shows case detail in sidebar
- ✅ **"Open Case →" button** navigates to Opinions page

### Test Result: ☐ Pass / ☐ Fail

**Notes**:
```
[Your observations here]
```

---

## Test Scenario 8: Edge Cases

**Purpose**: Test error handling

### Test 8A: Empty Query
1. Leave query box **empty**
2. Click **🔍 Search**

**Expected**: ✅ Error message or no-op (doesn't crash)

### Test 8B: No Results
1. Enter query: `zzzzz quantum flux capacitor zzzzz`
2. Click **🔍 Search**

**Expected**: ✅ Message like "No cases found" (doesn't crash)

### Test 8C: Very Long Query
1. Enter 500+ character query
2. Click **🔍 Search**

**Expected**: ✅ Handles gracefully (may truncate or return results)

### Test 8D: Missing API Key
1. Remove API key from `.env`
2. Restart app
3. Click **🚀 Ask AI**

**Expected**: ✅ Error message explaining API key needed

### Test Result: ☐ Pass / ☐ Fail

**Notes**:
```
[Your observations here]
```

---

## Test Scenario 9: Performance

**Purpose**: Measure response times

### Metrics to Record:

| Action | Expected Time | Actual Time | Pass? |
|---|---|---|---|
| 🔍 Search (retrieval only) | < 3 seconds | ___ sec | ☐ |
| 🚀 Ask AI (first token) | < 5 seconds | ___ sec | ☐ |
| 🚀 Ask AI (complete) | < 15 seconds | ___ sec | ☐ |
| Follow-up question | < 10 seconds | ___ sec | ☐ |

### Test Result: ☐ Pass / ☐ Fail

**Notes**:
```
[Performance observations]
```

---

## Test Scenario 10: UI/UX Quality

**Purpose**: Evaluate user experience

### Checklist:
- ☐ **Widget easy to find** (prominent on home page)
- ☐ **Query box large enough** (120px height)
- ☐ **Placeholder text helpful** (shows example queries)
- ☐ **Buttons clearly labeled** (🔍 Search vs 🚀 Ask AI)
- ☐ **Results readable** (good font size, spacing)
- ☐ **Mobile responsive** (if applicable)
- ☐ **No UI glitches** (overlapping elements, cut-off text)
- ☐ **Loading states clear** (spinners, progress indicators)
- ☐ **Error messages helpful** (actionable guidance)

### Test Result: ☐ Pass / ☐ Fail

**Notes**:
```
[UX observations]
```

---

## Summary Results

| Test Scenario | Status | Notes |
|---|---|---|
| 1. Basic Search | ☐ Pass / ☐ Fail | |
| 2. Case Detail Viewer | ☐ Pass / ☐ Fail | |
| 3. Navigation | ☐ Pass / ☐ Fail | |
| 4. API Key Config | ☐ Pass / ☐ Fail | |
| 5. AI Answer | ☐ Pass / ☐ Fail | |
| 6. Follow-Up Questions | ☐ Pass / ☐ Fail | |
| 7. Source Cards | ☐ Pass / ☐ Fail | |
| 8. Edge Cases | ☐ Pass / ☐ Fail | |
| 9. Performance | ☐ Pass / ☐ Fail | |
| 10. UI/UX Quality | ☐ Pass / ☐ Fail | |

**Overall Assessment**: ☐ Ready to Ship / ☐ Needs Work

---

## Debugging Checklist

If something doesn't work:

### Browser DevTools (F12)
1. Open **Console** tab
2. Look for JavaScript errors (red text)
3. Check **Network** tab for failed requests

### Streamlit Terminal Output
1. Look for Python exceptions
2. Check for "WARNING" or "ERROR" lines
3. Verify API key loaded (no warnings about missing key)

### Quick Fixes:
- **Search returns nothing**: Check corpus file exists (1.7 MB parquet)
- **AI doesn't answer**: Verify API key in .env, restart app
- **Slow performance**: Check TF-IDF index built (first search builds it)
- **UI looks broken**: Hard refresh browser (Cmd+Shift+R on Mac)

---

## Post-Test Actions

After completing all tests:

### If All Pass ✅
1. Document any performance observations
2. Note any UX improvements for future
3. Move to production deployment planning

### If Any Fail ❌
1. Note which test failed
2. Copy error messages from browser console
3. Copy stack traces from Streamlit terminal
4. Report findings for debugging

---

**Start Testing**: Open http://localhost:8507 now! 🚀
