"""Extract speaker statistics from oral argument transcripts.

This script processes individual oral argument JSON files to extract:
- Speaking time by role (Justice vs Counsel)
- Word counts by role
- Speaking pace (words per minute)
- Turn-taking patterns

Results are saved to oral_arguments_speaker_stats.json for use in the Streamlit app.

Usage:
    python scripts/extract_speaker_stats.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data" / "processed"
OA_DIR = DATA_DIR / "oral_arguments"
OUTPUT_FILE = DATA_DIR / "oral_arguments_speaker_stats.json"


def extract_speaker_stats(oa_json: dict[str, Any]) -> dict[str, Any]:
    """Extract speaker statistics from a single oral argument JSON.
    
    Args:
        oa_json: Oral argument JSON data
    
    Returns:
        Dict with speaker statistics
    """
    case_number = oa_json.get("case_number", "")
    segments = oa_json.get("segments", [])
    duration_seconds = oa_json.get("duration_seconds", 0)
    
    # Initialize counters
    stats = {
        "case_number": case_number,
        "total_duration": duration_seconds,
        "total_segments": len(segments),
        "justice_segments": 0,
        "counsel_segments": 0,
        "justice_time": 0.0,
        "counsel_time": 0.0,
        "justice_words": 0,
        "counsel_words": 0,
        "other_segments": 0,
        "other_time": 0.0,
        "other_words": 0,
    }
    
    for segment in segments:
        speaker = segment.get("display_speaker", "").lower()
        start = segment.get("start", 0)
        end = segment.get("end", 0)
        text = segment.get("text", "")
        
        segment_duration = end - start
        word_count = len(text.split())
        
        if "justice" in speaker or "chief" in speaker:
            stats["justice_segments"] += 1
            stats["justice_time"] += segment_duration
            stats["justice_words"] += word_count
        elif "counsel" in speaker or "attorney" in speaker:
            stats["counsel_segments"] += 1
            stats["counsel_time"] += segment_duration
            stats["counsel_words"] += word_count
        else:
            stats["other_segments"] += 1
            stats["other_time"] += segment_duration
            stats["other_words"] += word_count
    
    # Calculate derived metrics
    stats["justice_time_pct"] = (stats["justice_time"] / duration_seconds * 100) if duration_seconds > 0 else 0
    stats["counsel_time_pct"] = (stats["counsel_time"] / duration_seconds * 100) if duration_seconds > 0 else 0
    stats["justice_pace_wpm"] = (stats["justice_words"] / (stats["justice_time"] / 60)) if stats["justice_time"] > 0 else 0
    stats["counsel_pace_wpm"] = (stats["counsel_words"] / (stats["counsel_time"] / 60)) if stats["counsel_time"] > 0 else 0
    stats["justice_avg_segment_words"] = (stats["justice_words"] / stats["justice_segments"]) if stats["justice_segments"] > 0 else 0
    stats["counsel_avg_segment_words"] = (stats["counsel_words"] / stats["counsel_segments"]) if stats["counsel_segments"] > 0 else 0
    
    return stats


def main():
    if not OA_DIR.exists():
        print(f"ERROR: Oral arguments directory not found: {OA_DIR}", file=sys.stderr)
        sys.exit(1)
    
    json_files = list(OA_DIR.glob("*.json"))
    print(f"Found {len(json_files)} oral argument JSON files")
    
    all_stats = []
    
    for i, json_file in enumerate(json_files, 1):
        if i % 100 == 0:
            print(f"  Processed {i}/{len(json_files)}...")
        
        try:
            with open(json_file, 'r', encoding='utf-8') as f:
                oa_data = json.load(f)
            
            stats = extract_speaker_stats(oa_data)
            all_stats.append(stats)
        
        except Exception as e:
            print(f"  WARNING: Failed to process {json_file.name}: {e}", file=sys.stderr)
            continue
    
    print(f"\nExtracted statistics for {len(all_stats)} arguments")
    
    # Save results
    print(f"Writing results to {OUTPUT_FILE.name}...")
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        json.dump(all_stats, f, indent=2, ensure_ascii=False)
    
    # Print summary
    print("\nSummary:")
    total_justice_time = sum(s["justice_time"] for s in all_stats)
    total_counsel_time = sum(s["counsel_time"] for s in all_stats)
    total_time = total_justice_time + total_counsel_time
    
    print(f"  Total speaking time: {total_time / 3600:.1f} hours")
    print(f"  Justice speaking time: {total_justice_time / 3600:.1f} hours ({total_justice_time/total_time*100:.1f}%)")
    print(f"  Counsel speaking time: {total_counsel_time / 3600:.1f} hours ({total_counsel_time/total_time*100:.1f}%)")
    print(f"  Average Justice pace: {sum(s['justice_pace_wpm'] for s in all_stats if s['justice_pace_wpm'] > 0) / len([s for s in all_stats if s['justice_pace_wpm'] > 0]):.0f} words/min")
    print(f"  Average Counsel pace: {sum(s['counsel_pace_wpm'] for s in all_stats if s['counsel_pace_wpm'] > 0) / len([s for s in all_stats if s['counsel_pace_wpm'] > 0]):.0f} words/min")
    
    print("\nDone!")


if __name__ == "__main__":
    main()
