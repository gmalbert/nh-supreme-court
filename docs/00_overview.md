# NH Supreme Court Analyzer — Project Roadmap
*A Streamlit application for exploring New Hampshire Supreme Court opinions and case orders*

---

## Project Vision

Build a Streamlit-based web application that scrapes, parses, and analyzes NH Supreme Court opinions and case orders — giving legal researchers, journalists, attorneys, and curious citizens an interactive tool to explore the court's work, voting patterns, and legal trends.

This is the NH-specific counterpart to the SCOTUS Scrutiny app (Oyez-based), adapted for the realities of NH: **no structured API**, PDFs as the primary source, a small court of 5 justices, and a mix of precedential opinions and non-precedential case orders.

---

## Document Index

| File | Contents |
|------|----------|
| `00_overview.md` | This file — vision, scope, project structure |
| `01_data_collection.md` | Scraping strategy, PDF parsing, data schema |
| `02_data_schema.md` | Full field-by-field data model |
| `03_features.md` | All planned app features organized by page |
| `04_justice_reference.md` | Known justices, extraction logic, vote parsing |
| `05_streamlit_architecture.md` | App structure, pages, tech stack |
| `06_phased_plan.md` | Phase-by-phase build sequence |

---

## Court Background

The NH Supreme Court has **5 justices**: a Chief Justice and four Associate Justices. As of the 2026 opinions reviewed:

- **Gordon J. MacDonald** — Chief Justice
- **James P. Donovan** — Associate Justice (frequent opinion author)
- **Anna Barbara Hantz Marconi** — Associate Justice
- **Patrick E. Countway** — Associate Justice
- **Timothy J. Gould** — Associate Justice
- **James B. Will** — Associate Justice *(appears in Freese — may be a newer member or fill-in)*

> Note: NH occasionally has 5+ names appear due to retirements, appointments, and temporary assignments. The parser must handle panels smaller than 5 and `sat for oral argument but subsequently disqualified` notices.

**Two source types:**
- **Opinions** — precedential, full published opinions with citation format `20XX N.H. [number]`
- **Case Orders** — non-precedential administrative/procedural orders; useful for tracking docket activity

**Primary URL patterns:**
- Opinions: `https://www.courts.nh.gov/our-courts/supreme-court/orders-and-opinions/opinions/[YEAR]`
- Case Orders: `https://www.courts.nh.gov/our-courts/supreme-court/orders-and-opinions/case-orders/[YEAR]`

---

## Key Constraints vs. SCOTUS App

| Constraint | Impact |
|------------|--------|
| No structured API (unlike Oyez) | Must scrape HTML + parse PDFs |
| PDFs are the canonical source | Need robust PDF-to-text pipeline |
| Small court (5 justices) | Agreement matrices are small but meaningful |
| ~50–100 opinions/year | Rich per-case analysis feasible; no need to sample |
| Non-precedential orders | Useful for docket tracking, not for legal analysis |
| Per curiam opinions common | Author attribution not always available |
| Recusals and disqualifications | Must parse and track explicitly |
| Case numbers follow pattern `20XX-XXXX` | Good unique identifier |
| NH Citation format: `20XX N.H. [seq]` | Parseable for ordering |

---

## Guiding Design Principles

1. **Opinions first, orders second** — opinions are the analytical core; orders inform docket activity.
2. **Justice-centric views** — with only 5 seats, every vote matters and is trackable.
3. **Statutory interpretation is NH's bread and butter** — the three sample opinions all turn on statutory construction. Tag and surface this.
4. **Accessible to non-lawyers** — plain-language summaries, clear vote counts, no assumed legal knowledge.
5. **Streamlit-native** — use `st.tabs`, `st.expander`, sidebar filters, `st.dataframe`, Plotly/Altair charts.
6. **Data lives in flat files** — JSON or CSV in a `data/` folder, refreshed by scripts. No database required initially.
