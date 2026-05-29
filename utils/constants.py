"""
Constants for the NH Supreme Court Analyzer (Granite State Appeals).
"""

# ── Justice roster ────────────────────────────────────────────────────────────
JUSTICE_KEYS = [
    "macdonald",
    "donovan",
    "hantz_marconi",
    "bassett",
    "hicks",
    "countway",
    "gould",
    "will",
    "lynn",
]

JUSTICE_DISPLAY = {
    "macdonald": "MacDonald, C.J.",
    "donovan": "Donovan, J.",
    "hantz_marconi": "Hantz Marconi, J.",
    "bassett": "Bassett, J.",
    "hicks": "Hicks, J.",
    "countway": "Countway, J.",
    "gould": "Gould, J.",
    "will": "Will, J.",
    "lynn": "Lynn, C.J.",
    "per_curiam": "Per Curiam",
}

# Last-name → key mapping (uppercase → key) for vote parsing
JUSTICE_LAST_NAME_MAP = {
    "MACDONALD": "macdonald",
    "DONOVAN": "donovan",
    "HANTZ MARCONI": "hantz_marconi",
    "COUNTWAY": "countway",
    "GOULD": "gould",
    "WILL": "will",
    "HICKS": "hicks",
    "LYNN": "lynn",
    "BASSETT": "bassett",
}

# ── Vote types ─────────────────────────────────────────────────────────────────
VOTE_MAJORITY = "majority"
VOTE_DISSENT = "dissent"
VOTE_CONCUR_SEPARATE = "concur_separate"
VOTE_NOT_PARTICIPATING = "not_participating"
VOTE_RECUSED = "recused"
VOTE_DISQUALIFIED = "disqualified"

VOTE_DISPLAY = {
    "majority": "Majority",
    "dissent": "Dissent",
    "concur_separate": "Concurred Separately",
    "not_participating": "Not Participating",
    "recused": "Recused",
    "disqualified": "Disqualified",
}

VOTE_COLORS = {
    "majority": "#003057",       # NH blue — majority
    "dissent": "#C8102E",        # Red — dissent
    "concur_separate": "#F5A623",  # Amber — separate concurrence
    "not_participating": "#9E9E9E",  # Gray — not participating
    "recused": "#9E9E9E",
    "disqualified": "#9E9E9E",
}

# ── Outcome colors ─────────────────────────────────────────────────────────────
OUTCOME_COLORS = {
    "affirmed": "#2E7D32",              # green
    "reversed": "#C62828",             # red
    "remanded": "#F57C00",             # orange
    "reversed_and_remanded": "#E65100",  # deep orange
    "vacated": "#6A1B9A",              # purple
    "dismissed": "#546E7A",            # blue-grey
    "affirmed_and_remanded": "#1565C0",  # blue
}

OUTCOME_LABELS = {
    "affirmed": "Affirmed",
    "reversed": "Reversed",
    "remanded": "Remanded",
    "reversed_and_remanded": "Reversed & Remanded",
    "vacated": "Vacated",
    "dismissed": "Dismissed",
    "affirmed_and_remanded": "Affirmed & Remanded",
}

# ── Scraping ───────────────────────────────────────────────────────────────────
BASE_URL = "https://www.courts.nh.gov"
OPINIONS_URL_TEMPLATE = (
    "https://www.courts.nh.gov/our-courts/supreme-court/orders-and-opinions/opinions/{year}"
)
CASE_ORDERS_URL_TEMPLATE = (
    "https://www.courts.nh.gov/our-courts/supreme-court/orders-and-opinions/case-orders/{year}"
)

SCRAPE_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "Cache-Control": "max-age=0",
}

SCRAPE_DELAY_SECONDS = 1.0

# ── App settings ───────────────────────────────────────────────────────────────
APP_NAME = "Granite State Appeals"
APP_TAGLINE = "NH Supreme Court Analytics"
DATA_YEARS = list(range(2020, 2027))   # 2020 – 2026
PRIMARY_YEARS = [2024, 2025, 2026]
