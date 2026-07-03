# Casey Transcript Quality Scoring Methodology

## Overview

Every NH Supreme Court oral argument transcript is assigned an **operational quality score** from 0–100. This is a **no-reference** score — it evaluates the transcript's quality without requiring a human-generated reference transcript. The scorer uses heuristics to detect common Whisper transcription failures: muddled openings, repetition loops, over-merged segments, low language confidence, and speaker-boundary problems.

The score is not WER (word error rate). A score of 100 does not mean the transcript is word-perfect. It means the transcript passes all automated quality checks and exhibits no detectable failure modes.

---

## How Scoring Works

### Starting Score

Every transcript starts at **100** and is reduced by penalty deductions when specific failure signals are detected.

### Penalty Categories

#### 1. Opening Handoff (0–25 point deduction)

The opening of an oral argument is the most failure-prone section. Whisper sometimes misses the transition from the Justice's introduction to the attorney's opening statement, merging both into one segment or labeling the attorney's opening as a Justice.

The scorer looks for the phrase **"may it please the court"** (or "may i please the court") in the first several segments:

| Condition | Deduction |
|---|---|
| Phrase not found anywhere in the transcript | **−25** |
| Phrase found but after segment 8 | **−10** |
| Phrase found within first 8 segments | No deduction |

- **Segment 8** was determined empirically from a sample of clean NH Supreme Court transcripts. In a well-structured argument, counsel speaks by segment 3–5 at the latest.
- If the phrase is missing entirely, it likely means Whisper hallucinated or severely garbled the opening, which often correlates with broader quality issues throughout the transcript.

#### 2. First Segment Length (0–10 point deduction)

The very first Whisper segment should be a short exchange (typically the Justice calling the case). If the first segment is **120+ words**, it usually indicates Whisper merged the Justice's introduction and the attorney's opening into a single segment — a clear failure mode.

| Condition | Deduction |
|---|---|
| First segment ≥ 120 words | **−10** |

#### 3. Long Over-Merged Segments (up to 15 point deduction)

Whisper occasionally merges multiple speaker turns into one long segment. This produces segments with unusually high word counts, making the transcript hard to read and indicating poor speaker boundary detection.

The scorer calculates the **long segment ratio**:

```
long_segment_ratio = segments with ≥ 60 words / total segments
```

| Ratio | Deduction |
|---|---|
| Each 1% of long segments | −0.5 points (up to −15) |
| 0% | No deduction |

Additional penalty if **3+ segments exceed 100 words**:

| Condition | Deduction |
|---|---|
| Very long (≥100w) segments ≥ 3 | **−8** |

#### 4. Extreme Segment Length (0–10 point deduction)

If any single segment reaches **180+ words**, it's a strong signal of a major merge failure or hallucination.

| Condition | Deduction |
|---|---|
| Max segment words ≥ 180 | **−10** |

#### 5. Repeated / Looping Segments (up to 12 point deduction)

Whisper sometimes enters a loop, repeating the same segment text multiple times. The scorer detects this in two ways:

**Duplicate segment text** — identical non-empty segments appearing more than once:

```
repeated_segment_ratio = duplicate instances / total non-empty segments
```

| Ratio | Deduction |
|---|---|
| ≥ 3.0% | **−12** |
| ≥ 1.5% | **−6** |
| < 1.5% | No deduction |

**Repeated word windows** — identical 8-word sequences appearing in different parts of the transcript (indicates longer-range looping or drift):

```
repeated_window_density = repeated window instances / total words
```

| Density | Deduction |
|---|---|
| ≥ 2.0% | **−12** |
| ≥ 1.0% | **−6** |
| < 1.0% | No deduction |

Both can apply independently, so a severely looping transcript could lose up to **−24** from repetition alone.

#### 6. Low Language Confidence (0–5 point deduction)

Whisper reports a `language_probability` score indicating confidence that the audio is in the detected language. For English oral arguments, this should be near 1.0.

| Condition | Deduction |
|---|---|
| Language probability < 0.90 | **−5** |

---

## Final Score and Review Priority

After all deductions are applied, the score is clamped to `[0, 100]`.

| Score Range | Review Priority | Recommendation |
|---|---|---|
| **≥ 85** and no warnings | **Low** | Accept as-is |
| **75–84** | **Medium** | Review opening |
| **< 75** | **High** | Review and consider turbo rerun |

### Turbo Re-run Recommendation

A separate flag (`rerun_turbo_recommended`) is set to `True` if any of these conditions are met:

- Recommendation is already "review-and-consider-turbo-rerun"
- Opening counsel phrase was never detected
- Repeated window density ≥ 2.0%
- Opening counsel found after segment 20
- Opening counsel found after 120 seconds of audio

This flags transcripts that would most benefit from a second pass with the larger `turbo` Whisper model.

---

## Metrics Collected

For every scored transcript, the following metrics are also saved in `public/transcript_stats.json`:

| Group | Metrics |
|---|---|
| **Size** | segment_count, word_count, character_count |
| **Timing** | duration_seconds, duration_minutes |
| **Rate** | words_per_minute, segments_per_minute, questions_per_minute |
| **Opening** | opening_counsel_index, opening_counsel_start_seconds, opening_counsel_start_minutes |
| **Segment length** | long_segment_count, very_long_segment_count, max_segment_words, avg_words_per_segment, median_words_per_segment, p90_words_per_segment, avg_chars_per_segment, median_chars_per_segment, long_segment_ratio |
| **Repetition** | duplicate_segment_instances, repeated_segment_ratio, repeated_window_count, repeated_window_density |
| **Speaker** | speaker_guess_counts (Counsel/Justice), justice_guess_ratio, counsel_guess_ratio |
| **Language** | language, language_probability |
| **Questions** | question_segment_count, question_mark_count, exclamation_mark_count |
| **Model** | beam_size, compute_type |

---

## Limitations

This is a **no-reference heuristic scorer**. It can detect structural problems (muddled openings, repetition, over-merging) but cannot measure:

- **Accuracy of legal terminology** — it doesn't know if "habeas corpus" was transcribed as "have a corpus"
- **Named entity correctness** — it can't tell if "Chief Justice MacDonald" was transcribed correctly
- **Speaker identity** — it only checks for the presence of opening phrases, not who actually spoke
- **Word-level errors** — it has no reference transcript to compare against

For true accuracy measurement, a human-generated reference transcript would be needed for WER/CER calculation.
