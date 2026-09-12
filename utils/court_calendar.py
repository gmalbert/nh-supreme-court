"""NH Supreme Court calendar ingestion and neutral deadline arithmetic."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Iterable

import pandas as pd
import requests
from bs4 import BeautifulSoup


NH_COURT_CAL_URL = "https://www.courts.nh.gov/supreme-court/oral-arguments"
CALENDAR_COLUMNS = ["date", "docket", "case_name", "time", "source_url"]


def parse_oral_argument_schedule(html: str, source_url: str = NH_COURT_CAL_URL) -> pd.DataFrame:
    """Parse both table-based and linked-list versions of the court schedule."""
    soup = BeautifulSoup(html or "", "lxml")
    rows: list[dict[str, str]] = []
    for table_row in soup.select("table tr"):
        cells = [cell.get_text(" ", strip=True) for cell in table_row.select("th, td")]
        if len(cells) < 3 or cells[0].lower() in {"date", "argument date"}:
            continue
        rows.append(
            {
                "date": cells[0],
                "docket": cells[1],
                "case_name": cells[2],
                "time": cells[3] if len(cells) > 3 else "9:00 AM",
                "source_url": source_url,
            }
        )
    if not rows:
        docket_re = r"\b\d{4}-\d{3,4}\b"
        import re

        for item in soup.select("li, article, .views-row"):
            text = item.get_text(" ", strip=True)
            docket = re.search(docket_re, text)
            date_match = re.search(
                r"(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|June?|July?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\s+\d{1,2},\s+\d{4}",
                text,
                re.IGNORECASE,
            )
            if docket and date_match:
                rows.append(
                    {
                        "date": date_match.group(0),
                        "docket": docket.group(0),
                        "case_name": text,
                        "time": "9:00 AM",
                        "source_url": source_url,
                    }
                )
    return pd.DataFrame(rows, columns=CALENDAR_COLUMNS)


def fetch_oral_argument_schedule(
    url: str = NH_COURT_CAL_URL, *, timeout: int = 15
) -> pd.DataFrame:
    response = requests.get(
        url, headers={"User-Agent": "GraniteStateAppeals/1.0 (+public legal research)"}, timeout=timeout
    )
    response.raise_for_status()
    return parse_oral_argument_schedule(response.text, source_url=url)


def compute_filing_deadline(
    start: date | datetime,
    days: int,
    *,
    business_days: bool = False,
    holidays: Iterable[date] = (),
) -> date:
    """Perform transparent calendar arithmetic without interpreting court rules."""
    if days < 0:
        raise ValueError("days must be non-negative")
    current = start.date() if isinstance(start, datetime) else start
    holiday_set = set(holidays)
    if not business_days:
        return current + timedelta(days=days)
    remaining = days
    while remaining:
        current += timedelta(days=1)
        if current.weekday() < 5 and current not in holiday_set:
            remaining -= 1
    return current
