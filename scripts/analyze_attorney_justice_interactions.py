"""Analyze attorney-justice interaction patterns.

This script maps oral arguments to the justices on the bench at that time,
then analyzes which attorneys most frequently appear before which justices.

Usage:
    python scripts/analyze_attorney_justice_interactions.py
"""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data" / "processed"
JUSTICES_FILE = ROOT / "data" / "justices.json"
ORAL_ARGUMENTS_FILE = DATA_DIR / "oral_arguments.json"
ATTORNEY_STATS_FILE = DATA_DIR / "oral_arguments_attorney_stats.json"
OUTPUT_FILE = DATA_DIR / "attorney_justice_interactions.json"


def load_justices() -> list[dict]:
    """Load justice data with tenure dates."""
    with open(JUSTICES_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)


def get_justices_on_bench(argument_date: str, justices: list[dict]) -> list[str]:
    """Get list of justices on the bench for a given argument date."""
    if not argument_date:
        return []
    
    try:
        arg_date = datetime.strptime(argument_date, "%Y-%m-%d")
    except ValueError:
        return []
    
    bench = []
    for justice in justices:
        appointed = justice.get("date_appointed")
        retired = justice.get("date_retired")
        
        if not appointed:
            continue
        
        try:
            appointed_date = datetime.strptime(appointed, "%Y-%m-%d")
        except ValueError:
            continue
        
        # Check if justice was on bench at argument date
        if arg_date >= appointed_date:
            if retired:
                try:
                    retired_date = datetime.strptime(retired, "%Y-%m-%d")
                    if arg_date <= retired_date:
                        bench.append(justice["display_name"])
                except ValueError:
                    # If retired date is invalid, assume still on bench
                    bench.append(justice["display_name"])
            else:
                # No retirement date, assume still active
                bench.append(justice["display_name"])
    
    return bench


def analyze_interactions() -> dict[str, Any]:
    """Analyze attorney-justice interactions."""
    print("Loading data...")
    justices = load_justices()
    
    with open(ORAL_ARGUMENTS_FILE, 'r', encoding='utf-8') as f:
        oral_arguments = json.load(f)
    
    with open(ATTORNEY_STATS_FILE, 'r', encoding='utf-8') as f:
        attorney_data = json.load(f)
    
    case_attorneys = attorney_data["case_attorneys"]
    
    print(f"Analyzing {len(oral_arguments)} arguments...")
    
    # Track attorney-justice interactions
    attorney_justice_counts = defaultdict(lambda: defaultdict(int))
    justice_attorney_counts = defaultdict(lambda: defaultdict(int))
    justice_argument_counts = defaultdict(int)
    
    # Process each argument
    for i, arg in enumerate(oral_arguments, 1):
        if i % 100 == 0:
            print(f"  Processed {i}/{len(oral_arguments)}...")
        
        case_number = arg["case_number"]
        argument_date = arg.get("argument_date")
        
        if not argument_date:
            continue
        
        # Get justices on bench
        bench = get_justices_on_bench(argument_date, justices)
        if not bench:
            continue
        
        # Get attorneys for this case
        attorneys = case_attorneys.get(case_number, [])
        if not attorneys:
            continue
        
        # Record interactions
        for attorney in attorneys:
            attorney_name = attorney.get("name", "")
            if not attorney_name:
                continue
            
            for justice in bench:
                attorney_justice_counts[attorney_name][justice] += 1
                justice_attorney_counts[justice][attorney_name] += 1
        
        # Count arguments per justice
        for justice in bench:
            justice_argument_counts[justice] += 1
    
    # Build attorney interaction summaries
    attorney_interactions = []
    for attorney_name, justice_counts in attorney_justice_counts.items():
        interactions = []
        for justice, count in sorted(justice_counts.items(), key=lambda x: x[1], reverse=True):
            interactions.append({
                "justice": justice,
                "arguments": count
            })
        
        attorney_interactions.append({
            "attorney_name": attorney_name,
            "total_arguments": sum(justice_counts.values()),
            "justices_appeared_before": list(justice_counts.keys()),
            "interactions": interactions
        })
    
    # Sort by total arguments
    attorney_interactions.sort(key=lambda x: x["total_arguments"], reverse=True)
    
    # Build justice interaction summaries
    justice_interactions = []
    for justice, attorney_counts in justice_attorney_counts.items():
        interactions = []
        for attorney, count in sorted(attorney_counts.items(), key=lambda x: x[1], reverse=True)[:50]:
            interactions.append({
                "attorney": attorney,
                "arguments": count
            })
        
        justice_interactions.append({
            "justice": justice,
            "total_arguments": justice_argument_counts[justice],
            "unique_attorneys": len(attorney_counts),
            "top_attorneys": interactions
        })
    
    # Sort by total arguments
    justice_interactions.sort(key=lambda x: x["total_arguments"], reverse=True)
    
    return {
        "attorney_interactions": attorney_interactions,
        "justice_interactions": justice_interactions,
        "summary": {
            "total_arguments_analyzed": len([a for a in oral_arguments if a.get("argument_date")]),
            "unique_attorneys": len(attorney_justice_counts),
            "unique_justices": len(justice_attorney_counts)
        }
    }


def main():
    print("Analyzing attorney-justice interactions...")
    
    results = analyze_interactions()
    
    print(f"\nResults:")
    print(f"  Arguments analyzed: {results['summary']['total_arguments_analyzed']}")
    print(f"  Unique attorneys: {results['summary']['unique_attorneys']}")
    print(f"  Unique justices: {results['summary']['unique_justices']}")
    
    print(f"\nTop 5 most active justices:")
    for i, justice in enumerate(results["justice_interactions"][:5], 1):
        print(f"  {i}. {justice['justice']}: {justice['total_arguments']} arguments, {justice['unique_attorneys']} attorneys")
    
    print(f"\nTop 5 attorneys by arguments:")
    for i, attorney in enumerate(results["attorney_interactions"][:5], 1):
        print(f"  {i}. {attorney['attorney_name']}: {attorney['total_arguments']} arguments before {len(attorney['justices_appeared_before'])} justices")
    
    # Save results
    print(f"\nWriting results to {OUTPUT_FILE.name}...")
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    
    print("Done!")


if __name__ == "__main__":
    main()
