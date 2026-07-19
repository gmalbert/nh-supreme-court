# Chat Conversation Improvements — Historical Handoff

> Superseded by the home-page Ask & Browse implementation in `cases.py`. This
> document preserves the July 4 investigation and recommendations; it does not
> describe the current UI or retrieval scope. For current provider setup, see
> [`CHAT_PROVIDERS.md`](CHAT_PROVIDERS.md).

**Repository:** `supreme-court`
**Date:** 2026-07-04
**Purpose:** continue improving multi-turn legal chat in a new Codex thread.

## Current state

The chat assistant is working with these recent changes:

- Gemini 2.5 Flash is the default provider through Google's REST/SSE API.
- OpenCode Go remains an explicit backup; there is no automatic fallback.
- Provider and retrieval modules load only after the user clicks Send.
- Responses stream into the page.
- Follow-up suggestions are generated locally, avoiding a second model call.
- Chat source is currently limited to the U.S. Supreme Court.
- Case-card View buttons and narrative case links open the Cases page correctly.
- Case-name search covers the full local collection, including older terms.
- The newest assistant response is displayed at the top of the conversation.
- `.env` is loaded explicitly and supports:

```dotenv
CHAT_PROVIDER=gemini
GEMINI_API_KEY=...
```

Provider details are documented in `docs/CHAT_PROVIDERS.md`.

## Problem to solve next

Multi-turn follow-ups are not yet retrieval-aware. A question such as:

> Which later decisions expanded or limited these holdings?

is sent to TF-IDF as a standalone query. Because it contains no case names or
legal subject, retrieval returns unrelated cases matching generic words such as
"holdings," "limited," or "decisions." Gemini then correctly refuses to answer
because its supplied case material does not contain the requested holdings.

An observed bad response listed unrelated cases including:

- *Third National Bank in Nashville v. Impac Limited, Inc.*
- *Clay v. Sun Insurance Office, Limited*
- *The Wharf (Holdings) Ltd. v. United International Holdings*
- *Franchise Tax Board of California v. Alcan Aluminium, Limited*
- *Pioneer Investment Services Company v. Brunswick Associates Limited Partnership*

The refusal is appropriate; the retrieval context is the defect.

## Root causes

1. The former standalone `pages/14_Chat.py` called `retrieve_cases(user_input, ...)` using only the
   newest message.
2. Conversation history is passed to Gemini, but not to the retriever.
3. Pronouns and references such as "these cases," "that holding," "the
   dissent," and "the first case" are therefore unresolved during search.
4. `utils/chat_retriever.py` builds snippets primarily from
   `facts_of_the_case` and `question`; it does not reliably supply the case's
   `conclusion`/holding.
5. The local follow-up buttons include generic questions that omit the relevant
   case names or legal topic.

## Recommended implementation

### 1. Detect referential follow-ups

Add a small deterministic helper—no model call—that recognizes short or
referential questions containing phrases such as:

- these/those cases or holdings
- that case/holding/rule
- the dissent/majority
- the first/second/last case
- later decisions
- how did it/they

Keep false positives conservative.

### 2. Build a conversation-aware retrieval query

For an ordinary standalone question, search the question unchanged.

For a referential follow-up, construct a retrieval query from:

- the current question;
- the preceding user question;
- names of cases attached to the most recent assistant message.

Example:

```text
Current: Which later decisions expanded or limited these holdings?
Previous topic: What are the major exclusionary-rule cases?
Cases: Weeks v. United States; Mapp v. Ohio; United States v. Leon
```

Use this expanded text only for retrieval. Continue sending the user's original
wording to Gemini.

### 3. Preserve/reuse prior cases when appropriate

For questions specifically asking about the prior answer (facts, holding,
dissent, comparison), include the previous assistant message's attached cases
in the new context. Merge them with newly retrieved results, deduplicate by
`href`, and respect the cases-to-retrieve limit where practical.

For a direct question such as "What was the dissent in Mapp?", prioritize the
named/prior case rather than replacing it with semantically similar cases.

### 4. Add holdings to retrieved context

Update `utils/chat_retriever.py` to read and include at least:

- `facts_of_the_case`
- `question`
- `conclusion`
- optionally `description`

Do not put all fields into one 300-character snippet. Give the LLM labeled,
bounded fields such as Facts, Question, and Holding. Strip HTML before sending
the text and cap field lengths to control tokens.

Consider loading the relevant columns once through a cached href-indexed detail
table rather than re-reading the Parquet file separately for every result.

### 5. Improve local follow-up suggestions

Replace generic suggestions with case/topic-specific wording. For example:

- `What were the key facts in Mapp v. Ohio?`
- `How did United States v. Leon limit Mapp v. Ohio?`
- `Compare the reasoning in Mapp v. Ohio and Weeks v. United States.`

Avoid suggesting a later-decisions question unless the retrieved material can
support it or the next retrieval query will explicitly include the case names.

## Key files

- `cases.py` — current home-page Ask & Browse UI; `pages/14_Chat.py` was the historical standalone UI
- `utils/chat_retriever.py` — TF-IDF retrieval and context construction
- `utils/text_search.py` — local semantic index
- `utils/gemini_chat.py` — Gemini prompt and REST/SSE adapter
- `utils/chat_provider.py` — explicit provider selector
- `utils/opencode_chat.py` — retained OpenCode backup
- `utils/chat_formatter.py` — narrative links and source cards
- `tests/test_chat_providers.py` — provider-selection tests
- `tests/test_chat_navigation.py` — chat navigation tests

## Suggested tests

Add unit tests that do not call either provider:

1. A standalone question leaves its retrieval query unchanged.
2. "What was the dissent?" includes the previous question and previous case
   names in its retrieval query.
3. Prior and newly retrieved cases are deduplicated by `href`.
4. A prior explicitly referenced case is retained even when fresh TF-IDF
   results differ.
5. Formatted LLM context contains a labeled Holding when `conclusion` exists.
6. Missing holdings are represented honestly and never as `nan` or `None`.
7. Follow-up suggestions contain relevant case names.
8. The provider is not called while constructing the retrieval query.

## Manual acceptance flow

1. Clear Chat.
2. Ask: `What are the major Supreme Court cases concerning the exclusionary rule?`
3. Confirm the returned sources are relevant.
4. Ask: `Which later decisions expanded or limited these holdings?`
5. Confirm the second retrieval stays anchored to the first answer's cases.
6. Ask: `What did the dissent say?`
7. Confirm the answer identifies the relevant case or asks a narrow
   clarification if multiple dissents are possible.
8. Verify source-card View buttons and narrative links still open the exact
   case.
9. Confirm Gemini remains the active provider and no OpenCode request occurs.

## Guardrails

- Do not add a second model call merely to rewrite follow-up queries.
- Do not automatically fall back from Gemini to OpenCode.
- Do not send the entire case database or unlimited conversation history.
- Keep provider and retriever imports lazy so the Chat page remains fast.
- Preserve the model's instruction to admit when supplied material is
  insufficient; improve the supplied material instead of encouraging guesses.
