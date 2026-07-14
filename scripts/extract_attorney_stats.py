"""Extract attorney and firm data from oral argument metadata.

This script processes metadata.json files to extract attorney/firm information
and aggregate statistics for visualization.

Usage:
    python scripts/extract_attorney_stats.py
"""

from __future__ import annotations

import csv
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data" / "processed"
TRANSCRIPTS_DIR = Path("/Volumes/AI-Storage/nh-supreme-court-transcripts")
OUTPUT_FILE = DATA_DIR / "oral_arguments_attorney_stats.json"
ORAL_ARGUMENTS_FILE = DATA_DIR / "oral_arguments.json"
ATTORNEY_NAME_MAP_FILE = ROOT / "data" / "attorney_name_map.json"
FIRM_SOURCE_FILE = ROOT / "data" / "nh_supreme_court_firms_enriched_v7.csv"
CASE_ATTORNEY_OVERRIDES_FILE = ROOT / "data" / "case_attorney_overrides.json"
PDF_ATTORNEY_ROSTER_OVERRIDES_FILE = ROOT / "data" / "pdf_attorney_roster_overrides.json"
CASE_COUNSEL_FACTS_FILE = DATA_DIR / "case_counsel_sample_100.json"
PDF_ORAL_ROSTER_FILE = DATA_DIR / "oral_argument_roster.json"
NON_FIRM_STATUS_PREFIX = "skipped —"
EXCLUDED_ATTORNEY_NAMES = {
    "Union Academy",
    "View Video",
    "Your Honors",
    "Your Honours",
    "Your Honours.",
}
ATTORNEY_FIRM_OVERRIDES = {
    "Brittney M. White": "H&K",
    "Daniel E. Will": "NH Attorney General",
}


def load_oral_arguments() -> dict[str, dict]:
    """Load oral arguments data to get duration and date info."""
    with open(ORAL_ARGUMENTS_FILE, 'r', encoding='utf-8') as f:
        data = json.load(f)
    return {item["case_number"]: item for item in data}


def load_attorney_name_map() -> dict[str, str]:
    """Load manually reviewed attorney aliases and canonical names."""
    with open(ATTORNEY_NAME_MAP_FILE, 'r', encoding='utf-8') as f:
        data = json.load(f)
    return {
        alias: canonical
        for alias, canonical in data.items()
        if alias != "comment" and isinstance(canonical, str) and canonical.strip()
    }


def load_firm_name_map() -> dict[str, str]:
    """Load reviewed firm abbreviations from the canonical firm CSV.

    The annual-PDF parser can emit party labels and line-wrap fragments.  Only
    values explicitly present in the curated CSV may create a firm profile.
    """
    with open(FIRM_SOURCE_FILE, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        return {
            row["short_name"].strip(): row["full_name"].strip()
            for row in reader
            if (
                row.get("short_name", "").strip()
                and row.get("full_name", "").strip()
                and not row.get("review_status", "").strip().lower().startswith(NON_FIRM_STATUS_PREFIX)
            )
        }


def load_public_affiliation_map() -> dict[str, str]:
    """Load reviewed government/public entities for affiliations and comparisons."""
    with open(FIRM_SOURCE_FILE, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        affiliations = {}
        for row in reader:
            status = row.get("review_status", "").strip().lower()
            short_name = row.get("short_name", "").strip()
            display_name = row.get("full_name", "").strip() or short_name
            if not display_name or not status.startswith(NON_FIRM_STATUS_PREFIX):
                continue
            affiliations[display_name] = display_name
            if short_name:
                affiliations[short_name] = display_name
        return affiliations


def load_case_attorney_overrides() -> dict[str, list[dict[str, str]]]:
    """Load reviewed case rosters that replace incomplete source metadata."""
    if not CASE_ATTORNEY_OVERRIDES_FILE.exists():
        return {}
    with open(CASE_ATTORNEY_OVERRIDES_FILE, 'r', encoding='utf-8') as f:
        data = json.load(f)
    return {
        docket: attorneys
        for docket, attorneys in data.items()
        if docket != "comment" and isinstance(attorneys, list)
    }


def load_pdf_attorney_roster_overrides() -> dict[str, list[dict[str, str]]]:
    """Load reviewed oral-advocate rosters extracted from court archive PDFs."""
    if not PDF_ATTORNEY_ROSTER_OVERRIDES_FILE.exists():
        return {}
    with open(PDF_ATTORNEY_ROSTER_OVERRIDES_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    return {
        docket: attorneys
        for docket, attorneys in data.items()
        if docket != "comment" and isinstance(attorneys, list)
    }


def load_approved_oral_advocate_facts() -> dict[str, list[dict[str, str]]]:
    """Load only complete, approved evidence-backed oral-advocate rosters.

    A partially approved roster must not replace a case: doing so would turn an
    unresolved extraction issue into a false claim that no other attorney
    argued.  Facts remain available for review in the source dataset.
    """
    if not CASE_COUNSEL_FACTS_FILE.exists():
        return {}
    with open(CASE_COUNSEL_FACTS_FILE, "r", encoding="utf-8") as f:
        payload = json.load(f)
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for fact in payload.get("facts", []):
        if fact.get("role") == "oral_advocate" and fact.get("docket"):
            grouped[str(fact["docket"])].append(fact)
    approved: dict[str, list[dict[str, str]]] = {}
    for docket, facts in grouped.items():
        if not facts or any(fact.get("review_status") != "approved" for fact in facts):
            continue
        approved[docket] = [
            {
                "name": str(fact.get("attorney_canonical") or fact.get("attorney_raw") or ""),
                "firm": str(fact.get("firm") or ""),
                "side": str(fact.get("side") or "unknown"),
                "role": "oral_advocate",
                "source": str(fact.get("source_type") or ""),
            }
            for fact in facts
        ]
    return approved


def load_pdf_oral_rosters() -> dict[str, list[dict[str, str]]]:
    """Load annual-PDF oral-argument rosters as the profile/statistics source."""
    if not PDF_ORAL_ROSTER_FILE.exists():
        return {}
    with open(PDF_ORAL_ROSTER_FILE, "r", encoding="utf-8") as f:
        payload = json.load(f)
    rosters: dict[str, list[dict[str, str]]] = {}
    for item in payload.get("dockets", []):
        docket = str(item.get("docket") or "")
        entries = item.get("oral_argument_roster") or []
        if not docket or not isinstance(entries, list):
            continue
        rosters[docket] = [
            {
                "name": str(entry.get("attorney_raw") or ""),
                "firm": str(entry.get("firm") or ""),
                "side": str(entry.get("side") or "unknown"),
                "role": "oral_argument_roster",
                "source": "NH Supreme Court annual oral-argument archive PDF",
            }
            for entry in entries
        ]
    return rosters


def extract_attorney_data() -> dict[str, Any]:
    """Extract attorney data from all metadata files.
    
    Returns:
        Dict with case_attorneys, attorney_stats, firm_stats
    """
    # Load oral arguments for duration data
    oral_args = load_oral_arguments()
    attorney_name_map = load_attorney_name_map()
    firm_name_map = load_firm_name_map()
    public_affiliation_map = load_public_affiliation_map()
    case_attorney_overrides = load_case_attorney_overrides()
    pdf_attorney_overrides = load_pdf_attorney_roster_overrides()
    approved_oral_advocate_facts = load_approved_oral_advocate_facts()
    pdf_oral_rosters = load_pdf_oral_rosters()
    full_pdf_roster_available = PDF_ORAL_ROSTER_FILE.exists()
    
    case_attorneys = {}  # case_number -> list of attorneys
    attorney_cases = defaultdict(list)  # attorney_name -> list of cases
    firm_cases = defaultdict(list)  # firm_name -> list of cases
    attorney_firms = {}  # attorney_name -> primary firm
    
    # Find all metadata.json files
    metadata_files = list(TRANSCRIPTS_DIR.glob("*/*/*/metadata.json"))
    print(f"Found {len(metadata_files)} metadata files")
    
    for i, metadata_path in enumerate(metadata_files, 1):
        if i % 100 == 0:
            print(f"  Processed {i}/{len(metadata_files)}...")
        
        try:
            with open(metadata_path, 'r', encoding='utf-8') as f:
                metadata = json.load(f)
            
            case_number = metadata.get("docket_number")
            if full_pdf_roster_available:
                # Once the full annual-PDF roster exists, do not silently fill
                # its exception queue with unreliable transcript metadata.
                attorneys = pdf_oral_rosters.get(case_number, [])
            else:
                attorneys = approved_oral_advocate_facts.get(
                    case_number,
                    pdf_attorney_overrides.get(
                        case_number,
                        case_attorney_overrides.get(case_number, metadata.get("attorneys", [])),
                    ),
                )
            
            if not case_number or not attorneys:
                continue
            
            normalized_attorneys = []
            seen_attorneys = set()
            for attorney in attorneys:
                raw_name = (attorney.get("name") or "").strip()
                if not raw_name or raw_name in EXCLUDED_ATTORNEY_NAMES:
                    continue
                name = attorney_name_map.get(raw_name, raw_name).strip()
                if not name or name in seen_attorneys:
                    continue
                seen_attorneys.add(name)
                normalized_attorney = dict(attorney)
                normalized_attorney["name"] = name
                raw_firm = ATTORNEY_FIRM_OVERRIDES.get(
                    name, (attorney.get("firm") or "").strip()
                )
                normalized_attorney["firm"] = (
                    firm_name_map.get(raw_firm)
                    or public_affiliation_map.get(raw_firm)
                    or None
                )
                normalized_attorneys.append(normalized_attorney)

            if not normalized_attorneys:
                continue

            case_attorneys[case_number] = normalized_attorneys
            
            # Get duration and date from oral arguments data
            oa_data = oral_args.get(case_number, {})
            duration_seconds = oa_data.get("duration_seconds", 0)
            argument_date = oa_data.get("argument_date", "")
            
            # Aggregate by attorney
            for attorney in normalized_attorneys:
                name = (attorney.get("name") or "").strip()
                firm = (attorney.get("firm") or "").strip()
                
                if not name:
                    continue
                
                attorney_cases[name].append({
                    "case_number": case_number,
                    "side": attorney.get("side", ""),
                    "role": attorney.get("role", ""),
                    "duration_seconds": duration_seconds,
                    "argument_date": argument_date
                })
                
                if firm and name not in attorney_firms:
                    attorney_firms[name] = firm

                if firm:
                    firm_cases[firm].append({
                        "case_number": case_number,
                        "attorney": name,
                        "duration_seconds": duration_seconds,
                        "argument_date": argument_date
                    })
        
        except Exception as e:
            print(f"  WARNING: Failed to process {metadata_path}: {e}", file=sys.stderr)
            continue
    
    # Build attorney statistics
    attorney_stats = []
    for attorney_name, cases in attorney_cases.items():
        # Duration calculations
        durations = [c["duration_seconds"] for c in cases if c["duration_seconds"] > 0]
        total_duration = sum(durations)
        avg_duration = total_duration / len(durations) if durations else 0
        
        # Year-by-year breakdown
        year_counts = defaultdict(int)
        for case in cases:
            if case["argument_date"]:
                year = case["argument_date"][:4]
                year_counts[year] += 1
        
        stats = {
            "attorney_name": attorney_name,
            "firm": attorney_firms.get(attorney_name, ""),
            "total_arguments": len(cases),
            "cases": [c["case_number"] for c in cases],
            "total_duration_seconds": total_duration,
            "average_duration_seconds": avg_duration,
            "total_duration_hours": total_duration / 3600,
            "average_duration_minutes": avg_duration / 60,
            "years_active": dict(sorted(year_counts.items())),
            "first_argument_date": min((c["argument_date"] for c in cases if c["argument_date"]), default=""),
            "last_argument_date": max((c["argument_date"] for c in cases if c["argument_date"]), default=""),
            "sides": {
                "state": sum(1 for c in cases if c["side"] == "state"),
                "defendant": sum(1 for c in cases if c["side"] == "defendant"),
                "plaintiff": sum(1 for c in cases if c["side"] == "plaintiff"),
                "appellee": sum(1 for c in cases if c["side"] == "appellee"),
                "appellant": sum(1 for c in cases if c["side"] == "appellant"),
                "other": sum(1 for c in cases if c["side"] not in ["state", "defendant", "plaintiff", "appellee", "appellant"])
            }
        }
        attorney_stats.append(stats)
    
    # Build firm statistics
    firm_stats = []
    for firm_name, cases in firm_cases.items():
        # A case can have multiple advocates from the same firm.  It is one
        # oral argument for the firm's profile, not one argument per advocate.
        # Keep every attorney for the roster, but calculate firm totals from
        # unique dockets so the case table cannot contain duplicate rows.
        unique_cases = {}
        for case in cases:
            unique_cases.setdefault(case["case_number"], case)
        firm_case_rows = list(unique_cases.values())
        unique_attorneys = set(c["attorney"] for c in cases)
        
        # Duration calculations for firm
        durations = [c["duration_seconds"] for c in firm_case_rows if c["duration_seconds"] > 0]
        total_duration = sum(durations)
        avg_duration = total_duration / len(durations) if durations else 0
        
        # Year-by-year breakdown for firm
        year_counts = defaultdict(int)
        for case in firm_case_rows:
            if case["argument_date"]:
                year = case["argument_date"][:4]
                year_counts[year] += 1
        
        stats = {
            "firm_name": firm_name,
            "total_arguments": len(firm_case_rows),
            "unique_attorneys": len(unique_attorneys),
            "attorneys": sorted(unique_attorneys),
            "cases": [c["case_number"] for c in firm_case_rows],
            "total_duration_seconds": total_duration,
            "average_duration_seconds": avg_duration,
            "total_duration_hours": total_duration / 3600,
            "average_duration_minutes": avg_duration / 60,
            "years_active": dict(sorted(year_counts.items())),
            "first_argument_date": min((c["argument_date"] for c in firm_case_rows if c["argument_date"]), default=""),
            "last_argument_date": max((c["argument_date"] for c in firm_case_rows if c["argument_date"]), default="")
        }
        firm_stats.append(stats)
    
    # Sort by argument count
    attorney_stats.sort(key=lambda x: x["total_arguments"], reverse=True)
    firm_stats.sort(key=lambda x: x["total_arguments"], reverse=True)
    
    return {
        "case_attorneys": case_attorneys,
        "attorney_stats": attorney_stats,
        "firm_stats": firm_stats
    }


def main():
    print("Extracting attorney data from metadata files...")
    
    data = extract_attorney_data()
    
    print(f"\nExtracted data:")
    print(f"  Cases with attorney data: {len(data['case_attorneys'])}")
    print(f"  Unique attorneys: {len(data['attorney_stats'])}")
    print(f"  Unique firms: {len(data['firm_stats'])}")
    
    # Save results
    print(f"\nWriting results to {OUTPUT_FILE.name}...")
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    
    # Print top attorneys
    print("\nTop 10 attorneys by argument count:")
    for i, attorney in enumerate(data["attorney_stats"][:10], 1):
        print(f"  {i}. {attorney['attorney_name']} ({attorney['firm']}): {attorney['total_arguments']} arguments")
    
    # Print top firms
    print("\nTop 10 firms by argument count:")
    for i, firm in enumerate(data["firm_stats"][:10], 1):
        print(f"  {i}. {firm['firm_name']}: {firm['total_arguments']} arguments ({firm['unique_attorneys']} attorneys)")
    
    print("\nDone!")


if __name__ == "__main__":
    main()
