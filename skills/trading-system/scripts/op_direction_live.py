#!/usr/bin/env python3
"""Fetch one registered pool and optional leader candidates in one validated call."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

from op_pool import is_mainboard, load_pools


ROOT = Path(__file__).resolve().parent.parent
ASTOCK = os.environ.get("ASTOCK_BIN", str(ROOT.parent.parent / "astock" / "astock"))


def quote(codes: list[str]) -> list[dict]:
    result = subprocess.run(
        [ASTOCK, "live", "quote", *codes, "--json"],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise SystemExit(result.stderr.strip() or result.stdout.strip() or "astock quote failed")
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"astock returned invalid JSON: {exc}") from exc
    if not isinstance(payload, list):
        raise SystemExit("astock quote response is not a list")
    return payload


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("pool_id")
    parser.add_argument("--candidate", action="append", default=[])
    parser.add_argument(
        "--mainboard-only",
        action="store_true",
        help="quote only executable mainboard members; use this before any buy decision",
    )
    parser.add_argument("--json", action="store_true", dest="as_json")
    args = parser.parse_args()
    pool = load_pools()["pools"].get(args.pool_id)
    if pool is None:
        raise SystemExit(f"unknown pool: {args.pool_id}")
    codes = [code for code in pool["codes"] if not args.mainboard_only or is_mainboard(code)]
    candidates = args.candidate or []
    unknown = sorted(set(candidates) - set(codes))
    if unknown:
        raise SystemExit(f"candidate outside registered pool: {', '.join(unknown)}")
    raw_quotes = quote(codes)
    # TDX emits placeholder rows with price=0 before a valid auction quote.
    # Treat them as missing so they cannot become false -100% direction votes.
    quotes = [item for item in raw_quotes if float(item.get("price") or 0) > 0]
    returned = {str(item.get("code")) for item in quotes}
    missing = [code for code in codes if code not in returned]
    output = {
        "pool_id": args.pool_id,
        "direction": pool["direction"],
        "expected_count": len(codes),
        "mainboard_only": args.mainboard_only,
        "mainboard_codes": [code for code in pool["codes"] if is_mainboard(code)],
        "research_only_codes": [code for code in pool["codes"] if not is_mainboard(code)],
        "returned_count": len(quotes),
        "missing_codes": missing,
        "candidates": candidates,
        "quotes": quotes,
    }
    if args.as_json:
        print(json.dumps(output, ensure_ascii=False))
        return 0
    print(f"{pool['direction']} [{args.pool_id}] coverage {len(quotes)}/{len(codes)}")
    if not args.mainboard_only:
        research_only = [code for code in pool["codes"] if not is_mainboard(code)]
        if research_only:
            print(f"research-only non-mainboard: {' '.join(research_only)}")
    if missing:
        print(f"missing: {' '.join(missing)}")
    for item in quotes:
        marker = " <candidate>" if str(item.get("code")) in candidates else ""
        print(f"{item.get('code')} {item.get('price')} {item.get('change_pct', 0):+.2f}%{marker}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
