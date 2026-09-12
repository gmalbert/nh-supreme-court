"""Generate or deliver the Granite State Appeals weekly digest."""

from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from utils.court_calendar import fetch_oral_argument_schedule
from utils.data_loader import load_opinions
from utils.weekly_digest import build_weekly_digest_html, send_weekly_digest


def configured_recipients(value: str | None = None) -> list[str]:
    """Parse a query-free deployment recipient list from configuration."""
    configured = value if value is not None else os.environ.get("DIGEST_RECIPIENTS", "")
    return list(
        dict.fromkeys(
            address.strip()
            for address in re.split(r"[,;\s]+", configured)
            if address.strip()
        )
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="outputs/weekly_digest.html")
    parser.add_argument("--send-to", nargs="*", default=[])
    parser.add_argument(
        "--send-configured",
        action="store_true",
        help="Also send to DIGEST_RECIPIENTS when it is configured.",
    )
    arguments = parser.parse_args()
    try:
        schedule = fetch_oral_argument_schedule()
    except Exception:
        schedule = None
    body = build_weekly_digest_html(load_opinions(), schedule)
    output = ROOT / arguments.output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(body, encoding="utf-8")
    print(f"Wrote {output}")
    recipients = list(arguments.send_to)
    if arguments.send_configured:
        recipients.extend(configured_recipients())
    recipients = list(dict.fromkeys(address for address in recipients if address))
    if recipients:
        send_weekly_digest(recipients, body)
        print(f"Sent digest to {len(recipients)} recipient(s)")
    elif arguments.send_configured:
        print("DIGEST_RECIPIENTS is empty; generated the digest without delivery")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
