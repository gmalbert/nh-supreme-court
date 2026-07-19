# NH Supreme Court Case Digest & Holdings Database — Planning Document

**Goal:** Turn 24 years of NH Supreme Court opinions into a fast, reliable study tool — organized by topic, with every important rule of law traced back to the case (and quoted/paraphrased language) that established it. Built to get you from "reasonably informed lawyer" to "ready to sit on the bench" quickly.

**Not legal advice, not a substitute for reading the actual opinions before relying on anything in an official capacity** — this is a research accelerant, not authority.

---

## 1. What already exists (from the `nh-supreme-court` repo)

Before designing anything new, worth being explicit about what you've already built, so this project extends it instead of duplicating it:

- `data/processed/opinions.csv` and `all_opinions.json` — full opinion metadata + (per the README) full text, across the whole archive.
- `topics` column already on each opinion, backed by `data/topic_taxonomy.json`.
- `rsa_citations` column — statutory citations already extracted per case.
- A citation explorer already exists on the site — "which cases a decision cites and which later decisions cite it."
- Full-text search across the whole opinion archive.
- `scripts/build_dataset.py` — the pipeline that assembles the master CSV/JSON from raw sources.

**What's missing, based on what you asked for:**
1. A plain-language *summary* of each case (facts, procedural posture, holding, disposition).
2. Not just "Case A cites Case B" but *what Case A cited Case B for* — the actual proposition, with the quoted or closely-paraphrased language.
3. A topic-level roll-up: for a given subject (e.g., "notice before tax deed," "due process — property," "standard of review — summary judgment"), a synthesized outline of the governing rules in this jurisdiction, in the order they developed, so you can read one page instead of thirty cases.

That's the gap this plan fills.

---

## 2. Data model

New structured record **per opinion** (joins to your existing `opinions.csv` on citation/docket number):

```json
{
  "citation": "2026 N.H. 27",
  "case_name": "Manutsom v. Town of Hollis",
  "docket": "2025-0249",
  "date_issued": "2026-07-17",
  "topics": ["due process", "tax liens/deeds", "municipal law", "notice"],
  "disposition": "affirmed in part, reversed in part, remanded",
  "summary": "2-4 sentence plain-language summary of facts + outcome",
  "procedural_posture": "appeal from grant of summary judgment to defendant",
  "holdings": [
    {
      "rule": "Once a tax collector executes a deed divesting the owner of title, post-deed correspondence does not satisfy Jones v. Flowers' requirement of an 'additional reasonable step' before a taking.",
      "topic": "due process — notice before taking",
      "quoted_language": "its post-deed correspondences with the plaintiff did not constitute an 'additional reasonable step[]'",
      "quote_is_verbatim": true
    }
  ],
  "cites": [
    {
      "cited_case": "Jones v. Flowers",
      "citation": "547 U.S. 220 (2006)",
      "cited_for": "government must take additional reasonable steps if it learns notice failed, before taking property",
      "quoted_language": "when mailed notice of a tax sale is returned unclaimed, the State must take additional reasonable steps..."
    }
  ],
  "extraction_model": "claude-sonnet-5",
  "extraction_date": "2026-08-01",
  "needs_review": false
}
```

**Added after the Phase 0 sample run (see Section 7):** two fields the schema was missing —
- `"opinion_type"` (`"full opinion"` / `"summary order"` / `"3JX order"` / etc.) and `"precedential": true|false` — you confirmed you want everything included, so this is how a non-precedential order gets flagged rather than silently mixed in with binding authority.
- `"separate_opinions": [{"judge": ..., "type": "concurrence"|"dissent", "summary": ...}]` — the Hagenbuch sample has a substantive special concurrence flagging unresolved regulatory questions, which is exactly the kind of thing a judge-prep tool should surface rather than drop.

**Added after the second Phase 0 round:** a parallel, lighter-weight bucket —
- **`"discretion_calls": [{"topic": ..., "issue": ..., "outcome": "sustained"|"reversed"|..., "key_facts": ...}]`** — for the fact-bound "was this exercise of discretion sustainable" applications that show up constantly in family-law and evidentiary-ruling cases (e.g., Letendre's "trial court could value closely-held stock using the company's own redemption price without an independent appraisal," or Hall's "this confession was voluntary despite officers falsely suggesting they had forensic evidence"). These aren't portable rules of law the way "abrogation of common law requires clear statutory intent" is — they're illustrative data points about how a specific set of facts got decided. Keeping them separate from `holdings` means a topic brief can lead with the actual black-letter rules and use the discretion calls as a "here's how this has played out in practice" appendix, rather than diluting the rule list with one-off fact patterns.

Two things worth deciding now:
- **`holdings` vs `cites`** are different tables conceptually — `holdings` is "rules *this* case established," `cites` is "rules this case *borrowed* from elsewhere." Both matter for judge-prep (you want to know both what NH has held and what authority it leans on), so both get extracted.
- Cap `quoted_language` at short verbatim phrases (this mirrors sound practice regardless of source) — the point of this database is the *rule*, in plain language, not a wall of block quotes you'd need to re-verify against the reporter anyway.

---

## 3. Pipeline

**Phase 0 — Inventory & benchmark (do this before spending real money)**
- Confirm full opinion text actually exists for all 24 years in `all_opinions.json` (older years may be thinner/OCR'd).
- Get a real count of opinions to process (my rough guess is 2,000–3,500 full opinions across 24 years, but your data will tell you exactly).
- Hand-pick ~15–20 cases spanning different eras and topics (including this tax-deed case) and run the extraction prompt against them with 2-3 candidate models. Read the output critically before committing to a model for the full run. This step is cheap and will save you from re-running 3,000 cases because the schema or prompt needed tweaking.

**Phase 1 — Bulk extraction (Batch API)**
- One JSON-schema extraction call per opinion, run via the Batch API (roughly half price, no rush).
- Model choice: Claude Haiku 4.5 is very likely good enough for structured extraction (summary, disposition, topic tags, pulling out citations that already appear in the text) — this is a case where cost/quality tradeoff favors the cheap model, since the task is closer to "find and format" than "reason."
- Reserve Sonnet 5 (or Opus if you want maximum reliability) for the `holdings` extraction — identifying *which* propositions in a case are actually the operative rule (vs. dicta) is more judgment-heavy.
- Rough cost order-of-magnitude, batch-priced, for ~2,500 opinions at ~4,000-6,000 words each: **Haiku bulk pass ≈ $10-15. Sonnet holdings pass ≈ $25-50.** These are back-of-envelope estimates based on current published per-token rates — run the Phase 0 sample first and extrapolate from actual token counts rather than trusting this number.

**Phase 2 — Storage**
- New files alongside your existing data: `data/processed/case_digests.json` (summaries/holdings) and `data/processed/citation_propositions.json` (the enriched `cites` table).
- Keep it file-based/JSON like the rest of the repo rather than introducing a new DB engine, unless query performance becomes a problem — then SQLite is a natural upgrade since it's a single file and Streamlit/pandas both work with it easily.

**Phase 3 — Topic synthesis (the actual "study guide")**
- For each topic in your taxonomy, feed the model *all* the `holdings` tagged to that topic (deduplicated, chronologically ordered) and have it write a synthesized outline: current rule, how it developed, any splits/tensions between panels, most-cited case for each sub-rule.
- For topics that accumulate a meaningful number of `discretion_calls` (family law and evidentiary rulings especially), append a short "how this plays out in practice" section listing the fact patterns and outcomes, clearly separated from the black-letter rules above it — illustrative, not doctrinal.
- This is the highest-value, lowest-volume step (maybe 30-60 topic documents instead of thousands of case documents) — worth using Sonnet or Opus here regardless of the model choice above.
- Output: one markdown file per topic, e.g. `docs/topic-briefs/due-process-notice.md`.

**Phase 4 — Review pass**
- Spot-check a random ~5% sample of holdings/quotes against the source PDFs. LLM extraction of legal holdings can misattribute dicta as holding or get a citation slightly wrong — for something you're using to prep for a judgeship, a lightweight verification pass matters more than usual.
- Flag anything the model itself expresses uncertainty about (`needs_review: true`) for manual check first.

**Phase 5 — Site integration (later, per your answer)**
- New Streamlit page (`pages/topic_briefs.py` or similar) following the existing `utils/data_loader.py` pattern, surfacing the topic briefs and letting the case-level holdings show up inline on existing opinion pages.

---

## 4. Execution order

No practice-area prioritization needed since you said no preference — simplest path is chronological or just "whatever order the existing scraper already processes files in," since Phase 1 is a flat batch job anyway (order doesn't affect cost or quality). Topic synthesis (Phase 3) naturally happens after *all* of Phase 1 is done for a given topic, since it needs the full set of holdings to synthesize well — so Phase 3 will lag Phase 1 by however long the batch jobs take (batch API turnaround can be hours).

## 5. Open questions — answered

1. **Full text availability:** confirmed — full opinion text exists for all 24 years.
2. **Non-precedential/unpublished orders:** include everything, but tag each record with `opinion_type` and `precedential` (see schema update above) so a topic brief can lean on binding authority while still surfacing persuasive-only material clearly labeled as such.
3. **Taxonomy:** expand it — proposal in Section 6, validated against nine benchmark cases across every major practice area (Section 7).

## 6. Proposed expanded taxonomy (two-level: area > issue)

The existing `topic_taxonomy.json` looked flat/broad ("criminal law," "civil disputes," "family matters"). For judge-prep, you'll want to search by the actual legal issue, not just the case's general subject. Based on the nine benchmark cases now processed (Section 7) — spanning constitutional, property, family, trusts, administrative, criminal, evidentiary, and tort law — a two-level structure holds up well:

- **Constitutional Law** — Due Process (Notice Before Taking / Procedural Due Process generally), Equal Protection, State Constitution Provides Greater Protection Than Federal
- **Property & Municipal Law** — Tax Liens & Deeds, Zoning/Land Use, Eminent Domain, Landlord-Tenant (Quiet Enjoyment/Unauthorized Entry)
- **Family Law** — Third-Party Visitation & Standing, Divorce (Marital Property Division, Alimony), Child Protection
- **Trusts & Estates** — Discretionary Trust Distributions, Fiduciary Duty, Will Contests
- **Administrative Law** — Certiorari Review, Agency Deference, Public Benefits (SNAP/Medicaid/etc.)
- **Statutory Interpretation** — Abrogation of Common Law, Plain-Meaning Analysis, Federal Regulation Interpretation, Definition of "Willful"/"Willfully"
- **Civil Procedure** — Standard of Review (de novo/abuse of discretion/clear error), Standing, Waiver, Summary Judgment, Discovery Sanctions (Expert Witness Disclosure)
- **Criminal Law** — Self-Defense & Use of Deadly Force, Falsifying Physical Evidence
- **Criminal Procedure** — Sufficiency of the Evidence (Circumstantial), Interstate Agreement on Detainers/Speedy Trial, Preservation of Issues for Appeal, Confession Voluntariness/Motion to Suppress, Mistrial Standard
- **Evidence** — Rule 403 Balancing (Probative Value vs. Unfair Prejudice), Specific Contradiction/Opening the Door Doctrine, Prior Bad Acts (Rule 404(b) vs. Intrinsic/Same-Episode Evidence), Business/Stock Valuation, Expert Testimony (Medical Causation Opinions)
- **Torts** — Medical Malpractice (Proximate Cause), Negligence (Cause-in-Fact & Legal Cause)

This lets a single case tag multiple issue-level topics (Manutsom hits three: due process notice, tax liens/deeds, *and* summary judgment standard) rather than being forced into one bucket — which matches how you'll actually want to search when prepping ("show me every case on standard of review for a motion to dismiss," not just "show me the family law cases"). All eleven top-level areas now have at least one real sample behind them (Section 7).

## 7. Phase 0 benchmark — sample run (9 cases) — practice-area coverage complete

Nine cases now processed against the schema, spanning 2002-2026 and every major practice area: Manutsom (tax deed/due process), Willeke (great-grandparent visitation standing), Hagenbuch (food-stamp/trust-income certiorari), Harris (murder appeal: Rule 403, self-defense instruction, sufficiency of circumstantial evidence), Laforest (IAD speedy trial, statutory interpretation), Letendre (divorce: marital property division, alimony, expert-disclosure sanctions, stock valuation), Hall (confession voluntariness, mistrial standard, prior-bad-acts), Rood v. Moore (landlord-tenant quiet enjoyment, definition of "willful"), and now **Beckles v. Madden** — a genuine medical malpractice negligence case on proximate cause and expert-testimony sufficiency at summary judgment. Full structured output: **`case_digest_samples.json`**.

What this round surfaced:
- The schema and two-level taxonomy hold up cleanly across nine case types spanning 24 years — no further structural changes needed.
- **Two more real cross-case connections turned up**, on top of the Elementis Chem./Dorfsman one from round one: *State v. Lambert* (2001) supplies the "unsustainable exercise of discretion" standard both in Hall (2002) *and* in Harris (2025) — the same 24-year-old citation still doing identical work in a case decided this year. That's a strong, concrete argument for the topic-synthesis step: some standard-of-review rules are essentially permanent fixtures, and a judge-prep brief on "standard of review — evidentiary rulings" should say so explicitly rather than making you notice the pattern by re-reading two dozen separate opinions.
- Family/divorce cases (Letendre) pull in a genuinely different flavor of holding than the others so far — heavily fact-bound "was this discretion sustainable" rulings rather than clean statutory or constitutional rules. **Resolved:** split these into a separate `discretion_calls` bucket (see Section 2 update above) — Letendre and Hall have both been reprocessed with their fact-bound applications moved out of `holdings` and into `discretion_calls`, leaving `holdings` for portable rules only. Letendre ended up with 5 holdings / 5 discretion calls; Hall with 6 holdings / 3 discretion calls.

**Beckles closes the outstanding gap.** It's a real negligence-family tort (medical malpractice), and it also reinforces a pattern already seen in Manutsom: the court explicitly rejected a party's attempt to apply a *more deferential* standard of review to summary judgment than de novo — another concrete data point for how firmly "summary judgment gets de novo review" is entrenched across decades and case types (constitutional, family, and now tort).

**Practice-area coverage after 9 cases:** Constitutional Law, Property/Municipal Law, Family Law, Trusts & Estates, Administrative Law, Statutory Interpretation, Civil Procedure, Criminal Law, Criminal Procedure, Evidence, and Torts. Every major area from Section 6's taxonomy now has at least one real sample behind it, and the schema (holdings / discretion_calls / cites / separate_opinions) hasn't needed a structural change since the discretion_calls split. **Calling Phase 0 done** — the schema, taxonomy, and cost-estimate approach in Section 3 are ready to carry into Phase 1 whenever you want to move forward with the real batch run. If you want to sanity-check actual token counts before spending anything, I can also compute those directly from these nine samples rather than continuing to estimate.
