# Frontier Enhancement Blueprint

This document is additive to `ROADMAP.md`, `12_MONTH_ROADMAP.md`, the oral-argument plans, attorney analytics, and the hybrid-retrieval roadmap. Those documents already cover search, chat, citation networks, outcome prediction, transcript statistics, and public-facing analytics. The proposals below focus on gaps: legal-authority status, claim-level evidence, time-aware research, extraction uncertainty, and reproducible public data.

## 1. Build a time-aware authority graph

A citation edge is not enough for legal research. Classify how a later opinion treats an earlier one (`followed`, `distinguished`, `limited`, `questioned`, `overruled`) and preserve the exact supporting span. Make every status query relative to an `as_of_date`; otherwise a historically correct answer can silently use future law.

```python
from dataclasses import dataclass
from datetime import date

@dataclass(frozen=True)
class Treatment:
    citing_case: str
    cited_case: str
    label: str
    confidence: float
    evidence_start: int
    evidence_end: int
    decided_on: date
    extractor_version: str

def controlling_treatments(edges, case_id: str, as_of: date):
    return [e for e in edges if e.cited_case == case_id and e.decided_on <= as_of]
```

Start with high-precision rules around citation windows, then train a legal-text classifier from reviewed examples. Display the label only when confidence exceeds a per-class threshold; otherwise show “treatment unclear” and the passage.

## 2. Add claim-level answer verification

The current retrieval work is case-oriented. Add a second pass that decomposes an answer into factual/legal claims and requires each claim to be entailed by a quoted source span. Unsupported claims should be removed, not merely accompanied by a generic disclaimer.

```python
class VerifiedClaim(BaseModel):
    claim: str
    case_id: str
    source_span: str
    start_char: int
    end_char: int
    entailment_score: float

def publishable(claim: VerifiedClaim) -> bool:
    return claim.entailment_score >= 0.82 and len(claim.source_span.split()) >= 6
```

Create an evaluation set containing pinpoint questions, negative-premise questions, conflicting authorities, and “no answer in corpus” cases. Gate releases on citation precision, answer coverage, unsupported-claim rate, and temporal leakage.

## 3. Treat extraction confidence as first-class data

PDF parsing, speaker attribution, attorney normalization, and vote parsing should emit field-level provenance rather than a single record-level success flag.

```sql
CREATE TABLE field_observation (
  record_id TEXT NOT NULL,
  field_name TEXT NOT NULL,
  value_json TEXT,
  source_url TEXT NOT NULL,
  source_sha256 TEXT NOT NULL,
  page_number INTEGER,
  confidence DOUBLE,
  method TEXT NOT NULL,
  extractor_version TEXT NOT NULL,
  observed_at TIMESTAMP NOT NULL,
  PRIMARY KEY (record_id, field_name, source_sha256, extractor_version)
);
```

Rank the human-review queue by expected analytical impact: low confidence multiplied by the number of downstream charts/search results affected. Reviewed corrections become labeled examples for active learning.

## 4. Add doctrinal issue lifecycle views

Create normalized “issue threads” that connect cases asking substantially the same question. Show the first appearance, controlling rule changes, unresolved splits, and latest treatment. Unlike topic labels, a thread is a specific legal proposition with dated states.

Suggested UI:

- A timeline with rule-state changes and quoted holding text.
- An “authority as of” date control.
- Side-by-side majority/dissent proposition cards.
- A diff view showing which language was added, narrowed, or abandoned.
- Stable URLs such as `?issue=qualified-immunity-01&as_of=2024-01-01`.

## 5. Build a researcher workspace

Allow users to collect cases and transcript moments into a local workspace, annotate them, compare holdings, and export a citation-ready research packet. Store only case IDs, offsets, notes, and corpus version; resolve display text at render time so saved work remains auditable.

```python
workspace = {
    "schema_version": 1,
    "corpus_version": manifest["content_sha256"],
    "items": [{"case_id": case_id, "kind": "holding", "start": 412, "end": 690}],
    "notes": [],
}
```

Exports should include source URLs, retrieval date, page/pinpoint references, and a machine-readable JSON appendix.

## 6. Publish versioned data releases

Create a manifest for every public snapshot with schema version, row counts, source coverage, hashes, known exclusions, and transformation commit. Keep immutable dated releases and a `latest.json` pointer. Add a compatibility check before the Streamlit app loads a new release.

```python
def assert_compatible(manifest: dict) -> None:
    if manifest["schema_major"] != 1:
        raise RuntimeError("Unsupported corpus schema")
    if manifest["quality"]["missing_decision_date_rate"] > 0.01:
        raise RuntimeError("Release fails decision-date gate")
```

## 7. Evaluation and rollout

1. Establish gold sets for treatment labels, holding spans, speaker attribution, counsel identity, and temporal research answers.
2. Ship provenance and review queues before adding new derived metrics.
3. Release authority graphs behind a “beta” label with visible evidence.
4. Add telemetry for zero-result searches, citation clicks, correction submissions, and answer abstentions without logging sensitive query text by default.
5. Promote a feature only after slice-level checks by year, document quality, case type, and low-frequency justice/attorney.

The north-star metric should be verified research tasks completed, not raw page views or generated-answer count.
