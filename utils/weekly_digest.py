"""Weekly opinion digest generation and explicit SMTP delivery."""

from __future__ import annotations

import html
import os
import smtplib
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Iterable

import pandas as pd


def build_weekly_digest_html(
    opinions: pd.DataFrame,
    schedule: pd.DataFrame | None = None,
    *,
    as_of: datetime | None = None,
) -> str:
    now = as_of or datetime.now(timezone.utc)
    frame = opinions.copy()
    issued = pd.to_datetime(frame.get("date_issued"), errors="coerce", utc=True)
    recent = frame[issued >= pd.Timestamp(now) - pd.Timedelta(days=7)].copy()
    recent["_issued"] = issued.loc[recent.index]
    recent = recent.sort_values("_issued", ascending=False)

    decision_rows = []
    for _, row in recent.head(10).iterrows():
        decision_rows.append(
            "<tr>"
            f"<td>{html.escape(str(row.get('case_number', '')))}</td>"
            f"<td>{html.escape(str(row.get('case_name', '')))}</td>"
            f"<td>{html.escape(str(row.get('outcome', '')).replace('_', ' ').title())}</td>"
            f"<td>{html.escape(str(row.get('date_issued', ''))[:10])}</td>"
            "</tr>"
        )
    if not decision_rows:
        decision_rows.append('<tr><td colspan="4">No new opinions in this period.</td></tr>')

    schedule_rows = []
    if schedule is not None:
        for _, row in schedule.head(8).iterrows():
            schedule_rows.append(
                "<tr>"
                f"<td>{html.escape(str(row.get('date', '')))}</td>"
                f"<td>{html.escape(str(row.get('docket', '')))}</td>"
                f"<td>{html.escape(str(row.get('case_name', '')))}</td>"
                "</tr>"
            )
    if not schedule_rows:
        schedule_rows.append('<tr><td colspan="3">No upcoming schedule entries loaded.</td></tr>')

    return f"""<!doctype html>
<html><body style="font-family:Arial,sans-serif;color:#1f2937">
<h2 style="color:#003057">Granite State Appeals — Weekly Digest</h2>
<p>Generated {now.date().isoformat()} from the versioned public corpus.</p>
<h3>Recent decisions</h3>
<table border="1" cellpadding="6" cellspacing="0" style="border-collapse:collapse;width:100%">
<tr><th>Docket</th><th>Case</th><th>Disposition</th><th>Decided</th></tr>
{''.join(decision_rows)}
</table>
<h3>Upcoming oral arguments</h3>
<table border="1" cellpadding="6" cellspacing="0" style="border-collapse:collapse;width:100%">
<tr><th>Date</th><th>Docket</th><th>Case</th></tr>
{''.join(schedule_rows)}
</table>
<p style="color:#667085;font-size:12px">For research and public information; not legal advice.</p>
</body></html>"""


def send_weekly_digest(
    recipients: Iterable[str],
    html_body: str,
    *,
    subject: str = "NH Supreme Court Weekly Digest",
    smtp_host: str | None = None,
    smtp_port: int = 465,
    smtp_user: str | None = None,
    smtp_password: str | None = None,
    sender: str | None = None,
) -> None:
    recipient_list = [address.strip() for address in recipients if address.strip()]
    if not recipient_list:
        raise ValueError("At least one recipient is required")
    host = smtp_host or os.environ["SMTP_HOST"]
    user = smtp_user or os.environ["SMTP_USER"]
    password = smtp_password or os.environ["SMTP_PASS"]
    from_address = sender or os.environ.get("SMTP_FROM") or user
    message = MIMEMultipart("alternative")
    message["Subject"] = subject
    message["From"] = from_address
    message["To"] = ", ".join(recipient_list)
    message.attach(MIMEText(html_body, "html", "utf-8"))
    with smtplib.SMTP_SSL(host, smtp_port) as client:
        client.login(user, password)
        client.sendmail(from_address, recipient_list, message.as_string())
