"""
Annual report generation with PDF export.
Generates year-in-review reports with statistics, trends, and key cases.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Optional

import pandas as pd


def generate_year_stats(opinions_df: pd.DataFrame, year: int) -> dict:
    """
    Generate statistics for a specific year.
    
    Args:
        opinions_df: Full opinions DataFrame
        year: Year to analyze
    
    Returns:
        Dict with year statistics
    """
    # Filter to year
    if "citation_year" in opinions_df.columns:
        year_df = opinions_df[opinions_df["citation_year"] == year]
    elif "date_issued" in opinions_df.columns:
        opinions_df["date_issued"] = pd.to_datetime(opinions_df["date_issued"], errors="coerce")
        year_df = opinions_df[opinions_df["date_issued"].dt.year == year]
    else:
        return {}
    
    if year_df.empty:
        return {}
    
    stats = {
        "year": year,
        "total_opinions": len(year_df),
        "outcomes": year_df["outcome"].value_counts().to_dict() if "outcome" in year_df.columns else {},
        "top_authors": year_df["author"].value_counts().head(5).to_dict() if "author" in year_df.columns else {},
        "top_topics": {},
        "trial_courts": year_df["lower_court_type"].value_counts().to_dict() if "lower_court_type" in year_df.columns else {},
    }
    
    # Topics (handle list columns)
    if "topics" in year_df.columns:
        topics_series = year_df["topics"].dropna()
        if not topics_series.empty:
            # Explode list values
            if isinstance(topics_series.iloc[0], list):
                topics_flat = topics_series.explode()
                stats["top_topics"] = topics_flat.value_counts().head(10).to_dict()
            else:
                stats["top_topics"] = topics_series.value_counts().head(10).to_dict()
    
    # Disposition rates
    if "outcome" in year_df.columns:
        total = len(year_df)
        stats["affirmance_rate"] = (year_df["outcome"] == "Affirmed").sum() / total * 100 if total > 0 else 0
        stats["reversal_rate"] = (year_df["outcome"] == "Reversed").sum() / total * 100 if total > 0 else 0
    
    # Unanimity
    if "dissent" in year_df.columns:
        total = len(year_df)
        unanimous = (year_df["dissent"] == False).sum()
        stats["unanimity_rate"] = unanimous / total * 100 if total > 0 else 0
    
    return stats


def identify_notable_cases(year_df: pd.DataFrame, limit: int = 10) -> list[dict]:
    """
    Identify notable cases from the year.
    
    Criteria:
    - Reversals
    - Dissents
    - High citation count (if available)
    - Major topics
    
    Args:
        year_df: Opinions from the year
        limit: Max cases to return
    
    Returns:
        List of notable case dicts
    """
    notable = []
    
    # Reversals
    if "outcome" in year_df.columns:
        reversals = year_df[year_df["outcome"] == "Reversed"].head(limit // 2)
        for _, row in reversals.iterrows():
            notable.append({
                "case_number": row["case_number"],
                "case_name": row["case_name"],
                "citation": row.get("citation", ""),
                "reason": "Reversed lower court",
                "outcome": row["outcome"],
            })
    
    # Dissents
    if "dissent" in year_df.columns:
        dissents = year_df[year_df["dissent"] == True].head(limit // 2)
        for _, row in dissents.iterrows():
            notable.append({
                "case_number": row["case_number"],
                "case_name": row["case_name"],
                "citation": row.get("citation", ""),
                "reason": "Divided court",
                "outcome": row.get("outcome", ""),
            })
    
    return notable[:limit]


def generate_markdown_report(stats: dict, notable_cases: list[dict]) -> str:
    """
    Generate Markdown formatted annual report.
    
    Args:
        stats: Year statistics dict
        notable_cases: List of notable cases
    
    Returns:
        Markdown report text
    """
    year = stats.get("year", datetime.now().year)
    
    md_parts = [
        f"# New Hampshire Supreme Court",
        f"## {year} Year in Review\n",
        f"---\n",
        f"### Overview\n",
        f"The New Hampshire Supreme Court issued **{stats.get('total_opinions', 0)} opinions** in {year}.\n",
    ]
    
    # Outcomes
    if stats.get("outcomes"):
        md_parts.append("### Outcomes\n")
        for outcome, count in stats["outcomes"].items():
            md_parts.append(f"- **{outcome}:** {count}")
        md_parts.append("")
        
        if "affirmance_rate" in stats:
            md_parts.append(f"**Affirmance Rate:** {stats['affirmance_rate']:.1f}%")
        if "reversal_rate" in stats:
            md_parts.append(f"**Reversal Rate:** {stats['reversal_rate']:.1f}%\n")
    
    # Unanimity
    if "unanimity_rate" in stats:
        md_parts.append(f"**Unanimity Rate:** {stats['unanimity_rate']:.1f}%\n")
    
    # Top authors
    if stats.get("top_authors"):
        md_parts.append("### Most Prolific Authors\n")
        for author, count in list(stats["top_authors"].items())[:5]:
            md_parts.append(f"- **{author}:** {count} opinions")
        md_parts.append("")
    
    # Top topics
    if stats.get("top_topics"):
        md_parts.append("### Most Common Topics\n")
        for topic, count in list(stats["top_topics"].items())[:10]:
            md_parts.append(f"- **{topic}:** {count}")
        md_parts.append("")
    
    # Trial courts
    if stats.get("trial_courts"):
        md_parts.append("### Cases by Trial Court\n")
        for court, count in stats["trial_courts"].items():
            md_parts.append(f"- **{court}:** {count}")
        md_parts.append("")
    
    # Notable cases
    if notable_cases:
        md_parts.append("### Notable Cases\n")
        for case in notable_cases[:10]:
            md_parts.append(f"#### {case['case_name']}")
            md_parts.append(f"*{case['citation']}*")
            md_parts.append(f"**{case['reason']}** — Outcome: {case['outcome']}\n")
    
    md_parts.append("---")
    md_parts.append(f"\n*Report generated by Granite State Appeals on {datetime.now().strftime('%B %d, %Y')}*")
    
    return "\n".join(md_parts)


def export_to_pdf(markdown_text: str, output_path: Path) -> bool:
    """
    Export Markdown report to PDF using reportlab.
    
    Args:
        markdown_text: Markdown report text
        output_path: Path to save PDF
    
    Returns:
        True if successful
    """
    try:
        from reportlab.lib.pagesizes import letter
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.units import inch
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak
        from reportlab.lib.enums import TA_LEFT, TA_CENTER
        
        # Create PDF
        doc = SimpleDocTemplate(
            str(output_path),
            pagesize=letter,
            rightMargin=72,
            leftMargin=72,
            topMargin=72,
            bottomMargin=18,
        )
        
        # Styles
        styles = getSampleStyleSheet()
        title_style = ParagraphStyle(
            "CustomTitle",
            parent=styles["Heading1"],
            fontSize=24,
            textColor="darkblue",
            spaceAfter=30,
            alignment=TA_CENTER,
        )
        
        heading_style = styles["Heading2"]
        body_style = styles["BodyText"]
        
        # Parse markdown to story
        story = []
        lines = markdown_text.split("\n")
        
        for line in lines:
            line = line.strip()
            
            if not line:
                story.append(Spacer(1, 0.2*inch))
            elif line.startswith("# "):
                story.append(Paragraph(line[2:], title_style))
            elif line.startswith("## "):
                story.append(Paragraph(line[3:], title_style))
            elif line.startswith("### "):
                story.append(Paragraph(line[4:], heading_style))
            elif line.startswith("- "):
                story.append(Paragraph("• " + line[2:], body_style))
            elif line == "---":
                story.append(Spacer(1, 0.5*inch))
            else:
                story.append(Paragraph(line, body_style))
        
        # Build PDF
        doc.build(story)
        
        return True
    
    except ImportError:
        print("reportlab not installed. Install with: pip install reportlab")
        return False
    except Exception as e:
        print(f"Error generating PDF: {e}")
        return False


def generate_annual_report(
    opinions_df: pd.DataFrame,
    year: int,
    output_dir: Path,
    format: str = "markdown",
) -> Optional[Path]:
    """
    Generate complete annual report.
    
    Args:
        opinions_df: Full opinions DataFrame
        year: Year to generate report for
        output_dir: Directory to save report
        format: "markdown" or "pdf"
    
    Returns:
        Path to generated report file, or None if failed
    """
    # Generate stats
    stats = generate_year_stats(opinions_df, year)
    
    if not stats:
        print(f"No data found for year {year}")
        return None
    
    # Filter year data for notable cases
    if "citation_year" in opinions_df.columns:
        year_df = opinions_df[opinions_df["citation_year"] == year]
    else:
        opinions_df["date_issued"] = pd.to_datetime(opinions_df["date_issued"], errors="coerce")
        year_df = opinions_df[opinions_df["date_issued"].dt.year == year]
    
    notable_cases = identify_notable_cases(year_df)
    
    # Generate markdown
    markdown_text = generate_markdown_report(stats, notable_cases)
    
    # Save
    output_dir.mkdir(parents=True, exist_ok=True)
    
    if format == "pdf":
        output_path = output_dir / f"NH_Supreme_Court_{year}_Report.pdf"
        success = export_to_pdf(markdown_text, output_path)
        if success:
            return output_path
        else:
            # Fall back to markdown
            format = "markdown"
    
    if format == "markdown":
        output_path = output_dir / f"NH_Supreme_Court_{year}_Report.md"
        output_path.write_text(markdown_text, encoding="utf-8")
        return output_path
    
    return None
