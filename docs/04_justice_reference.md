# Justice Reference & Vote Parsing

## Active Justice Roster (as of 2026)

Based on the three sample opinions reviewed (Freese 2026 N.H. 18; Home Insurance 2026 N.H. 19; Metro Treatment 2026 N.H. 20):

| Key | Last Name | First Name | Display | Role | Status |
|-----|-----------|------------|---------|------|--------|
| `macdonald` | MacDonald | Gordon J. | MacDonald, C.J. | Chief Justice | Active (disqualified in Freese) |
| `donovan` | Donovan | James P. | Donovan, J. | Associate Justice | Active — authored Home Ins. and Metro |
| `countway` | Countway | Patrick E. | Countway, J. | Associate Justice | Active |
| `gould` | Gould | Timothy J. | Gould, J. | Associate Justice | Active |
| `will` | Will | James B. | Will, J. | Associate Justice | Active — appears in Freese |
| `hantz_marconi` | Hantz Marconi | Anna Barbara | Hantz Marconi, J. | Associate Justice | Did not appear in sample opinions — confirm status |

> **Note:** Will appears in Freese but not in Home Ins. or Metro. Hantz Marconi appears in none of the three samples. This likely reflects recusal patterns and case assignments, not departure from the court. The justice reference table should be populated from the court's official roster page and updated when appointments or retirements occur.

**Court website justice roster:** `https://www.courts.nh.gov/our-courts/supreme-court/justices`

---

## Historical Justices (for multi-year analysis)

The data pipeline must track justices who have since retired. Maintain `data/justices.json` with `is_active: false` and `date_retired` for former members. Relevant for any analysis going back to 2020+:

- **Hicks, J.** — retired; appeared in earlier opinions
- **Lynn, C.J.** — predecessor to MacDonald as CJ
- **Bassett, J.** — check tenure dates

Pull the complete historical roster from the court's website or archived opinions.

---

## Vote Line Parsing Logic

The concurrence/dissent block always appears at the very end of the opinion, after the holding. It follows consistent patterns.

### Pattern Catalog

**Pattern A — Full concurrence line with special notes:**
```
DONOVAN, COUNTWAY, GOULD, and WILL, JJ., concurred;
MACDONALD, C.J., sat for oral argument but subsequently disqualified himself
and did not participate in further review of the case.
```
→ Author: Per Curiam or implicit from body
→ Majority: Donovan, Countway, Gould, Will
→ Not Participating: MacDonald (disqualified)

**Pattern B — Simple concurrence (most common):**
```
MACDONALD, C.J., and COUNTWAY and GOULD, JJ., concurred.
```
→ Author is named in the byline above (e.g., "DONOVAN, J.")
→ Majority: Donovan (author) + MacDonald, Countway, Gould
→ Not Listed: Will, Hantz Marconi → mark as `not_participating` (absent from panel)

**Pattern C — With dissent:**
```
DONOVAN and GOULD, JJ., concurred; WILL, J., dissented.
```
→ Author: named in byline
→ Majority: [author] + Donovan, Gould
→ Dissent: Will

**Pattern D — With separate concurrence:**
```
COUNTWAY, J., concurred specially; DONOVAN and GOULD, JJ., concurred.
```
→ `concur_separate` for Countway

**Pattern E — Per curiam with all participating:**
```
MACDONALD, C.J., and DONOVAN, COUNTWAY, GOULD, and WILL, JJ., concurred.
```
→ Author: Per Curiam
→ All 5 in majority

### Parsing Algorithm

```python
def parse_vote_block(text: str, author: str) -> dict:
    """
    Extract the vote breakdown from the tail of an opinion.
    Returns dict mapping justice_key -> vote_type.
    """
    # 1. Extract the last ~500 characters of the opinion
    tail = text[-500:]
    
    # 2. Identify all justice mentions and their context
    # Pattern: NAME(S), (C.J.|J.) verb [; NAME, J., verb]*
    
    CONCUR_PATTERNS = [
        r"([A-Z\-]+(?:,?\s+[A-Z\-]+)*),\s+(?:C\.J\.|JJ?\.)(?:,| and)?\s+concurred",
    ]
    DISSENT_PATTERNS = [
        r"([A-Z\-]+),\s+J\.,\s+dissented",
    ]
    SEPARATE_PATTERNS = [
        r"([A-Z\-]+),\s+J\.,\s+concurred specially",
        r"([A-Z\-]+),\s+J\.,\s+concurred in part and dissented in part",
    ]
    NOT_PARTICIPATING_PATTERNS = [
        r"([A-Z\-]+),\s+C?\.?J\.,\s+(?:sat for oral argument but )?(?:subsequently )?disqualified",
        r"([A-Z\-]+),\s+C?\.?J\.,\s+did not participate",
        r"([A-Z\-]+),\s+C?\.?J\.,\s+recused",
    ]
    
    # 3. Map extracted names to justice keys using JUSTICE_NAME_MAP
    # 4. Add author to majority (if not per curiam, author is majority)
    # 5. Any justice in roster not mentioned → not_participating
    
    return votes_dict
```

### Justice Name Map

```python
JUSTICE_NAME_MAP = {
    "MACDONALD": "macdonald",
    "DONOVAN": "donovan", 
    "COUNTWAY": "countway",
    "GOULD": "gould",
    "WILL": "will",
    "HANTZ MARCONI": "hantz_marconi",
    "HICKS": "hicks",         # historical
    "LYNN": "lynn",           # historical
    "BASSETT": "bassett",     # historical
    # Add others as discovered
}
```

### Edge Cases to Handle

1. **"sat for oral argument but disqualified"** — distinct from simple recusal; preserve the note text
2. **"did not sit"** — appears in some older opinions
3. **Panels of 3** — occasionally a case is heard by only 3 justices; vote line may show only 3 names
4. **"on the brief only"** — some justices review briefs but don't participate in oral argument; still vote
5. **Retired justice finishing an opinion** — a justice who retires may still author an opinion argued before their departure; parse their name even if not in active roster
6. **Visiting/assigned judges** — NH may assign superior court judges to sit with the Supreme Court; these names won't be in the justice map; flag them as `visiting_judge`

---

## Author Detection

### Byline Patterns

The opinion author appears on its own line immediately after the counsel block:

```
DONOVAN, J.
[¶1] ...
```

or:

```
PER CURIAM.
[¶1] ...
```

### Author Normalization

```python
def extract_author(text: str) -> tuple[str, str]:
    """Returns (author_key, author_display)"""
    m = re.search(
        r"^(PER CURIAM|([A-Z\s\-]+),\s+(C\.J\.|J\.))\.\s*\n\s*\[¶1\]",
        text, re.MULTILINE
    )
    if not m:
        return "unknown", "Unknown"
    raw = m.group(1)
    if raw == "PER CURIAM":
        return "per_curiam", "Per Curiam"
    name = m.group(2).strip()
    key = JUSTICE_NAME_MAP.get(name, name.lower().replace(" ", "_"))
    display = m.group(0).rstrip(".\n")
    return key, display
```

---

## Justice Display in UI

### Bench Diagram (SVG or Plotly)

For the NH court's 5 seats, render a simple bench layout:

```
[Left 2]  [Left 1]  [CENTER / CJ]  [Right 1]  [Right 2]
```

Color each seat by vote:
- 🔵 Blue — majority
- 🔴 Red — dissent  
- 🟡 Yellow — concur separately
- ⬜ Gray — not participating / recused

Label each seat with the justice's last name and their vote.

### Vote Badge

Compact inline badge showing vote string and participant count:
- "5-0 (unanimous)"
- "4-1 (Will dissenting)"
- "4-0 (MacDonald disqualified)"
- "3-1-1 (Countway concurring)"

---

## Agreement Matrix Calculation

For any time window, compute pairwise agreement:

```python
def compute_agreement(opinions: list[dict], j1: str, j2: str) -> float:
    """
    Returns % of cases where j1 and j2 voted the same way,
    limited to cases where both participated.
    """
    shared = [
        op for op in opinions
        if op["votes"].get(j1, {}).get("vote") not in ("not_participating", "recused")
        and op["votes"].get(j2, {}).get("vote") not in ("not_participating", "recused")
    ]
    if not shared:
        return None
    same = sum(
        1 for op in shared
        if op["votes"][j1]["vote"] == op["votes"][j2]["vote"]
    )
    return same / len(shared)
```

With 5 justices there are 10 unique pairs — display all 10 in the heatmap.
