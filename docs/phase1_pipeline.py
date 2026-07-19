#!/usr/bin/env python3
"""
phase1_pipeline.py

Bulk-extraction pipeline for the NH Supreme Court case-digest database
(Phase 1 of the judge-prep project). Wraps the Anthropic Message Batches
API in four steps you run as separate commands, so a bad batch never
costs you more than the step you're on:

    build   -> read opinions, write batch_requests.jsonl (no API calls, free)
    submit  -> upload batch_requests.jsonl to the Batches API
    status  -> check / wait on a running batch
    fetch   -> download results, write case_digests.json + citation_propositions.json

Usage:
    python phase1_pipeline.py build   --manifest opinions/manifest.csv --input-dir opinions --out out/ [--limit N] [--model claude-sonnet-5]
    python phase1_pipeline.py submit  --requests out/batch_requests.jsonl --out out/
    python phase1_pipeline.py status  --batch-file out/batch_state.json [--wait]
    python phase1_pipeline.py fetch   --batch-file out/batch_state.json --out out/

Requires: pip install anthropic --break-system-packages
Requires: ANTHROPIC_API_KEY environment variable set.
"""
import argparse
import csv
import json
import sys
import time
from pathlib import Path

from phase1_schema import EXTRACTION_TOOL, SYSTEM_PROMPT, build_messages

DEFAULT_MODEL = "claude-sonnet-5"
MAX_TOKENS = 4096

# Rough chars-per-token used ONLY for the pre-flight cost estimate printed by
# `build`. This is a heuristic, not a tokenizer -- good enough to sanity-check
# an order of magnitude before you spend anything. Use the real usage figures
# in the batch results for actual accounting.
CHARS_PER_TOKEN_ESTIMATE = 4.0


def load_manifest(manifest_path: Path, input_dir: Path):
    """Read the opinions manifest (docket, case_name, citation, date_issued,
    court_below, file_path) and yield one dict per opinion with full_text loaded.

    Swap this function out if your source data lives in all_opinions.json
    instead of a CSV + text-file-per-opinion layout -- everything downstream
    only cares about the dict shape it returns.
    """
    with open(manifest_path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            text_path = input_dir / row["file_path"]
            if not text_path.exists():
                print(f"  [skip] missing text file for docket {row['docket']}: {text_path}", file=sys.stderr)
                continue
            row["full_text"] = text_path.read_text(encoding="utf-8")
            yield row


def already_processed_dockets(out_dir: Path) -> set:
    digest_file = out_dir / "case_digests.json"
    if not digest_file.exists():
        return set()
    existing = json.loads(digest_file.read_text(encoding="utf-8"))
    return {r["docket"] for r in existing}


def cmd_build(args):
    manifest_path = Path(args.manifest)
    input_dir = Path(args.input_dir)
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    skip_dockets = already_processed_dockets(out_dir) if args.skip_processed else set()

    opinions = list(load_manifest(manifest_path, input_dir))
    opinions = [o for o in opinions if o["docket"] not in skip_dockets]
    if args.limit:
        opinions = opinions[: args.limit]

    if not opinions:
        print("Nothing to build (all opinions already processed, or manifest empty).")
        return

    requests_path = out_dir / "batch_requests.jsonl"
    manifest_lookup = {}
    total_input_chars = 0

    with open(requests_path, "w", encoding="utf-8") as out_f:
        for op in opinions:
            messages = build_messages(
                case_name=op["case_name"], docket=op["docket"], citation=op["citation"],
                date_issued=op["date_issued"], court_below=op["court_below"],
                full_text=op["full_text"],
            )
            request_body = {
                "custom_id": op["docket"],
                "params": {
                    "model": args.model,
                    "max_tokens": MAX_TOKENS,
                    "system": SYSTEM_PROMPT,
                    "messages": messages,
                    "tools": [EXTRACTION_TOOL],
                    "tool_choice": {"type": "tool", "name": EXTRACTION_TOOL["name"]},
                },
            }
            out_f.write(json.dumps(request_body) + "\n")
            manifest_lookup[op["docket"]] = {
                k: op[k] for k in ("case_name", "citation", "date_issued", "court_below", "docket")
            }
            total_input_chars += len(messages[0]["content"]) + len(SYSTEM_PROMPT)

    (out_dir / "manifest_lookup.json").write_text(json.dumps(manifest_lookup, indent=2), encoding="utf-8")

    est_input_tokens = total_input_chars / CHARS_PER_TOKEN_ESTIMATE
    est_output_tokens = len(opinions) * 700  # rough: ~700 output tokens per structured digest
    print(f"Built {len(opinions)} requests -> {requests_path}")
    print(f"Rough token estimate: ~{est_input_tokens:,.0f} input, ~{est_output_tokens:,.0f} output "
          f"(heuristic, not a real tokenizer -- see the plan doc for per-model batch pricing math)")
    if args.dry_run:
        print("(--dry-run: stopping before submit. Inspect batch_requests.jsonl before spending anything.)")


def get_client():
    try:
        import anthropic
    except ImportError:
        sys.exit("Missing dependency. Run: pip install anthropic --break-system-packages")
    return anthropic.Anthropic()


def cmd_submit(args):
    from anthropic.types.message_create_params import MessageCreateParamsNonStreaming
    from anthropic.types.messages.batch_create_params import Request

    requests_path = Path(args.requests)
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    requests = []
    with open(requests_path, encoding="utf-8") as f:
        for line in f:
            body = json.loads(line)
            requests.append(Request(
                custom_id=body["custom_id"],
                params=MessageCreateParamsNonStreaming(**body["params"]),
            ))

    if not requests:
        sys.exit("No requests found in " + str(requests_path))
    if len(requests) > 100_000:
        sys.exit("Batch API caps at 100,000 requests per batch -- split the JSONL first.")

    client = get_client()
    batch = client.messages.batches.create(requests=requests)

    state = {"batch_id": batch.id, "processing_status": batch.processing_status,
              "submitted_count": len(requests)}
    (out_dir / "batch_state.json").write_text(json.dumps(state, indent=2), encoding="utf-8")
    print(f"Submitted batch {batch.id} ({len(requests)} requests). Status: {batch.processing_status}")
    print(f"State saved to {out_dir / 'batch_state.json'} -- use `status`/`fetch` with --batch-file pointing at it.")


def cmd_status(args):
    state_path = Path(args.batch_file)
    state = json.loads(state_path.read_text(encoding="utf-8"))
    client = get_client()

    while True:
        batch = client.messages.batches.retrieve(state["batch_id"])
        counts = batch.request_counts
        print(f"status={batch.processing_status} "
              f"processing={counts.processing} succeeded={counts.succeeded} "
              f"errored={counts.errored} canceled={counts.canceled} expired={counts.expired}")
        if batch.processing_status == "ended" or not args.wait:
            break
        time.sleep(args.poll_interval)

    state["processing_status"] = batch.processing_status
    state_path.write_text(json.dumps(state, indent=2), encoding="utf-8")


def cmd_fetch(args):
    state_path = Path(args.batch_file)
    out_dir = Path(args.out)
    state = json.loads(state_path.read_text(encoding="utf-8"))
    manifest_lookup = json.loads((out_dir / "manifest_lookup.json").read_text(encoding="utf-8"))

    client = get_client()
    batch = client.messages.batches.retrieve(state["batch_id"])
    if batch.processing_status != "ended":
        sys.exit(f"Batch not finished yet (status={batch.processing_status}). Run `status --wait` first.")

    digests = []
    citation_props = []
    needs_review_queue = []

    for result in client.messages.batches.results(state["batch_id"]):
        docket = result.custom_id
        meta = manifest_lookup.get(docket, {})

        if result.result.type != "succeeded":
            needs_review_queue.append({
                "docket": docket, "reason": result.result.type,
                "detail": getattr(getattr(result.result, "error", None), "message", None),
            })
            continue

        tool_use = next(
            (b for b in result.result.message.content if b.type == "tool_use"), None
        )
        if tool_use is None:
            needs_review_queue.append({"docket": docket, "reason": "no_tool_use_block"})
            continue

        digest = dict(tool_use.input)
        digest.update(meta)  # case_name/citation/date_issued/court_below/docket from source data
        digest["extraction_model"] = batch.id  # traceable back to the batch; swap for model name if preferred
        digests.append(digest)

        if digest.get("needs_review"):
            needs_review_queue.append({"docket": docket, "reason": "model_flagged",
                                        "note": digest.get("review_note")})

        for cite in digest.get("cites", []):
            citation_props.append({
                "citing_case": digest.get("case_name"), "citing_docket": docket,
                **cite,
            })

    out_dir.mkdir(parents=True, exist_ok=True)
    _merge_write(out_dir / "case_digests.json", digests, key="docket")
    _merge_write(out_dir / "citation_propositions.json", citation_props, key=None)
    if needs_review_queue:
        _merge_write(out_dir / "needs_review_queue.json", needs_review_queue, key="docket")

    print(f"Fetched {len(digests)} succeeded, {len(needs_review_queue)} flagged for review.")
    print(f"Wrote: {out_dir/'case_digests.json'}, {out_dir/'citation_propositions.json'}"
          + (f", {out_dir/'needs_review_queue.json'}" if needs_review_queue else ""))


def _merge_write(path: Path, new_records: list, key):
    """Append new_records to the JSON array at `path`, de-duping on `key` if given."""
    existing = json.loads(path.read_text(encoding="utf-8")) if path.exists() else []
    if key:
        existing = [r for r in existing if r.get(key) not in {n.get(key) for n in new_records}]
    existing.extend(new_records)
    path.write_text(json.dumps(existing, indent=2, ensure_ascii=False), encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    p_build = sub.add_parser("build", help="Build batch_requests.jsonl from source opinions (no API calls).")
    p_build.add_argument("--manifest", required=True)
    p_build.add_argument("--input-dir", required=True)
    p_build.add_argument("--out", required=True)
    p_build.add_argument("--model", default=DEFAULT_MODEL)
    p_build.add_argument("--limit", type=int, default=None)
    p_build.add_argument("--dry-run", action="store_true")
    p_build.add_argument("--skip-processed", action="store_true",
                          help="Skip dockets already present in out/case_digests.json")
    p_build.set_defaults(func=cmd_build)

    p_submit = sub.add_parser("submit", help="Submit batch_requests.jsonl to the Batches API.")
    p_submit.add_argument("--requests", required=True)
    p_submit.add_argument("--out", required=True)
    p_submit.set_defaults(func=cmd_submit)

    p_status = sub.add_parser("status", help="Check (or wait on) a submitted batch.")
    p_status.add_argument("--batch-file", required=True)
    p_status.add_argument("--wait", action="store_true")
    p_status.add_argument("--poll-interval", type=int, default=60)
    p_status.set_defaults(func=cmd_status)

    p_fetch = sub.add_parser("fetch", help="Download results and write case_digests.json / citation_propositions.json.")
    p_fetch.add_argument("--batch-file", required=True)
    p_fetch.add_argument("--out", required=True)
    p_fetch.set_defaults(func=cmd_fetch)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
