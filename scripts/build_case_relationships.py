"""
Build case relationships index linking opinions to case orders.
Normalizes docket numbers and creates bidirectional links.

Usage:
    python scripts/build_case_relationships.py
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from utils.oral_arguments import normalize_docket_numbers


def normalize_docket_for_orders(docket: str) -> list[str]:
    """
    Normalize docket number for order matching.
    Returns list of possible normalized forms.
    """
    if not docket or not isinstance(docket, str):
        return []

    # Use oral arguments normalization as base
    normalized = normalize_docket_numbers(docket)
    simple_match = re.fullmatch(r"(\d{4})-(\d{1,4})", docket.strip())
    if simple_match:
        year, sequence = simple_match.groups()
        normalized.extend([
            f"{year}-{int(sequence)}",
            f"{year}-{sequence.zfill(4)}",
        ])

    # Additional normalization for orders
    variants = set(normalized)

    for norm in normalized:
        # Remove leading zeros from sequence numbers
        norm_no_zeros = re.sub(r'-0+(\d+)', r'-\1', norm)
        variants.add(norm_no_zeros)


    return sorted(variants)


def match_orders_to_opinions(
    opinions_df: pd.DataFrame,
    orders_df: pd.DataFrame,
) -> dict:
    """
    Match case orders to opinions by docket number.

    Returns dict mapping case_number to related orders.
    """
    # Build opinion docket index
    opinion_index = {}
    for _, row in opinions_df.iterrows():
        case_number = row["case_number"]
        docket_variants = normalize_docket_for_orders(case_number)

        for variant in docket_variants:
            if variant not in opinion_index:
                opinion_index[variant] = []
            opinion_index[variant].append(case_number)

    # Match orders to opinions
    relationships = {}
    unmatched_orders = []

    for _, order_row in orders_df.iterrows():
        docket = order_row.get("docket_number", "")
        order_date = order_row.get("order_date", "")
        order_type = order_row.get("order_type", "")
        description = order_row.get("description", "")

        docket_variants = normalize_docket_for_orders(docket)

        matched_case_numbers: set[str] = set()
        for variant in docket_variants:
            matched_case_numbers.update(opinion_index.get(variant, []))

        for case_number in matched_case_numbers:
            relationships.setdefault(case_number, []).append({
                "docket_number": docket,
                "order_date": order_date,
                "order_type": order_type,
                "description": description,
            })

        if not matched_case_numbers:
            unmatched_orders.append({
                "docket_number": docket,
                "order_date": order_date,
                "order_type": order_type,
            })

    return relationships, unmatched_orders


def main():
    print("Building case relationships index...")

    # Load opinions
    opinions_csv = ROOT / "data" / "processed" / "opinions.csv"
    if not opinions_csv.exists():
        print(f"Error: {opinions_csv} not found")
        return 1

    print(f"Loading opinions from {opinions_csv}...")
    opinions_df = pd.read_csv(opinions_csv)
    print(f"Loaded {len(opinions_df)} opinions")

    # Load case orders
    orders_csv = ROOT / "data" / "processed" / "case_orders.csv"
    if not orders_csv.exists():
        print(f"Warning: {orders_csv} not found")
        print("No case orders to link.")
        # Create empty relationships file
        output_file = ROOT / "data" / "processed" / "case_relationships.json"
        with open(output_file, "w") as f:
            json.dump({}, f, indent=2)
        return 0

    print(f"Loading case orders from {orders_csv}...")
    orders_df = pd.read_csv(orders_csv)
    print(f"Loaded {len(orders_df)} case orders")

    # Match orders to opinions
    print("Matching orders to opinions...")
    relationships, unmatched = match_orders_to_opinions(opinions_df, orders_df)

    # Statistics
    opinions_with_orders = len(relationships)
    total_order_links = sum(len(orders) for orders in relationships.values())
    unmatched_count = len(unmatched)

    print(f"\nStatistics:")
    print(f"  Opinions with related orders: {opinions_with_orders}")
    print(f"  Total order-to-opinion links: {total_order_links}")
    print(f"  Unmatched orders: {unmatched_count}")

    # Save relationships
    output_file = ROOT / "data" / "processed" / "case_relationships.json"
    print(f"\nSaving relationships to {output_file}...")

    with open(output_file, "w") as f:
        json.dump(relationships, f, indent=2)

    # Save unmatched orders for review
    if unmatched:
        unmatched_file = ROOT / "data" / "processed" / "unmatched_orders.json"
        print(f"Saving unmatched orders to {unmatched_file}...")

        with open(unmatched_file, "w") as f:
            json.dump(unmatched[:100], f, indent=2)  # Save first 100

    print("✓ Case relationships index complete")

    return 0


if __name__ == "__main__":
    sys.exit(main())
