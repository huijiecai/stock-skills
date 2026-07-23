#!/usr/bin/env python3
"""Read and validate the trading system's executable direct-benefit pools."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
POOL_FILE = ROOT / "data" / "research" / "pools.json"
CODE_RE = re.compile(r"^[0-9]{6}$")
MAINBOARD_PREFIXES = ("000", "001", "002", "003", "600", "601", "603", "605")


def is_mainboard(code: str) -> bool:
    return str(code).startswith(MAINBOARD_PREFIXES)


def load_pools() -> dict:
    try:
        payload = json.loads(POOL_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemExit(f"pool registry invalid: {exc}") from exc
    pools = payload.get("pools")
    if not isinstance(pools, dict) or not pools:
        raise SystemExit("pool registry has no pools")
    for pool_id, pool in pools.items():
        codes = pool.get("codes") if isinstance(pool, dict) else None
        if not isinstance(codes, list) or not codes:
            raise SystemExit(f"{pool_id}: codes must be a non-empty list")
        if len(codes) != len(set(codes)) or any(not CODE_RE.match(str(code)) for code in codes):
            raise SystemExit(f"{pool_id}: duplicate or invalid stock code")
        expectation_file = pool.get("expectation_file") if isinstance(pool, dict) else None
        if not isinstance(expectation_file, str) or not expectation_file:
            raise SystemExit(f"{pool_id}: expectation_file is required")
        if not (ROOT / "data" / "research" / "expectations" / expectation_file).is_file():
            raise SystemExit(f"{pool_id}: expectation file not found: {expectation_file}")
    return payload


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("pool_id", nargs="?")
    parser.add_argument("--json", action="store_true", dest="as_json")
    parser.add_argument("--codes", action="store_true")
    parser.add_argument("--mainboard", action="store_true", help="show only executable mainboard codes")
    parser.add_argument("--validate", action="store_true")
    args = parser.parse_args()
    payload = load_pools()
    pools = payload["pools"]
    if args.validate:
        print(f"validated {len(pools)} pools")
        return 0
    if not args.pool_id:
        parser.error("pool_id is required unless --validate is used")
    pool = pools.get(args.pool_id)
    if pool is None:
        available = ", ".join(sorted(pools))
        raise SystemExit(f"unknown pool {args.pool_id!r}; available: {available}")
    codes = [code for code in pool["codes"] if not args.mainboard or is_mainboard(code)]
    if args.codes:
        print(" ".join(codes))
    elif args.as_json:
        print(json.dumps({
            "id": args.pool_id,
            **pool,
            "mainboard_codes": [code for code in pool["codes"] if is_mainboard(code)],
            "research_only_codes": [code for code in pool["codes"] if not is_mainboard(code)],
        }, ensure_ascii=False))
    else:
        print(f"{pool['direction']} ({args.pool_id})")
        print(f"expectation_file: {pool['expectation_file']}")
        print(f"codes ({len(codes)}): {' '.join(codes)}")
        if not args.mainboard:
            research_only = [code for code in pool["codes"] if not is_mainboard(code)]
            if research_only:
                print(f"research-only non-mainboard: {' '.join(research_only)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
