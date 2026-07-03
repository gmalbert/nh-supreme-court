"""Extract attorney and firm data from oral argument metadata.

This script processes metadata.json files to extract attorney/firm information
and aggregate statistics for visualization.

Usage:
    python scripts/extract_attorney_stats.py
"""

from __future__ import annotations

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
FIRM_NAME_MAP_FILE = ROOT / "data" / "firm_name_map.json"
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
    """Load manually reviewed firm abbreviations and canonical names."""
    with open(FIRM_NAME_MAP_FILE, 'r', encoding='utf-8') as f:
        data = json.load(f)
    return {
        alias: canonical
        for alias, canonical in data.items()
        if alias != "comment" and isinstance(canonical, str) and canonical.strip()
    }


def extract_attorney_data() -> dict[str, Any]:
    """Extract attorney data from all metadata files.
    
    Returns:
        Dict with case_attorneys, attorney_stats, firm_stats
    """
    # Load oral arguments for duration data
    oral_args = load_oral_arguments()
    attorney_name_map = load_attorney_name_map()
    firm_name_map = load_firm_name_map()
    
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
            attorneys = metadata.get("attorneys", [])
            
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
                if name in ATTORNEY_FIRM_OVERRIDES:
                    normalized_attorney["firm"] = ATTORNEY_FIRM_OVERRIDES[name]
                else:
                    raw_firm = (attorney.get("firm") or "").strip()
                    normalized_attorney["firm"] = firm_name_map.get(raw_firm, raw_firm) or None
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
                
                if firm:
                    firm_cases[firm].append({
                        "case_number": case_number,
                        "attorney": name,
                        "duration_seconds": duration_seconds,
                        "argument_date": argument_date
                    })
                    # Track primary firm for attorney
                    if name not in attorney_firms:
                        attorney_firms[name] = firm
        
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
        unique_attorneys = set(c["attorney"] for c in cases)
        
        # Duration calculations for firm
        durations = [c["duration_seconds"] for c in cases if c["duration_seconds"] > 0]
        total_duration = sum(durations)
        avg_duration = total_duration / len(durations) if durations else 0
        
        # Year-by-year breakdown for firm
        year_counts = defaultdict(int)
        for case in cases:
            if case["argument_date"]:
                year = case["argument_date"][:4]
                year_counts[year] += 1
        
        stats = {
            "firm_name": firm_name,
            "total_arguments": len(cases),
            "unique_attorneys": len(unique_attorneys),
            "attorneys": sorted(unique_attorneys),
            "cases": [c["case_number"] for c in cases],
            "total_duration_seconds": total_duration,
            "average_duration_seconds": avg_duration,
            "total_duration_hours": total_duration / 3600,
            "average_duration_minutes": avg_duration / 60,
            "years_active": dict(sorted(year_counts.items())),
            "first_argument_date": min((c["argument_date"] for c in cases if c["argument_date"]), default=""),
            "last_argument_date": max((c["argument_date"] for c in cases if c["argument_date"]), default="")
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
