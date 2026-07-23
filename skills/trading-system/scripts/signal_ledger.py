#!/usr/bin/env python3
"""Register and consume unique intraday trading signals.

The ledger prevents the same evidence from being counted as a second sell signal
on the same day. A new action requires a new fingerprint.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime
from pathlib import Path


LEDGER = Path(__file__).resolve().parent.parent / "data" / "signal_ledger.json"


def load() -> dict:
    try:
        payload = json.loads(LEDGER.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemExit(f"signal ledger invalid: {exc}") from exc
    if not isinstance(payload.get("signals"), list):
        raise SystemExit("signal ledger has no signals list")
    return payload


def save(payload: dict) -> None:
    temporary = LEDGER.with_suffix(".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(LEDGER)


def signal_id(kind: str, date: str, sequence: int) -> str:
    return f"{kind.upper()}-{date}-{sequence:02d}"


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)

    register = sub.add_parser("register")
    register.add_argument("--direction", required=True)
    register.add_argument("--kind", required=True, choices=["出口A", "出口B", "BUY", "ADD"])
    register.add_argument("--date", required=True, help="YYYYMMDD")
    register.add_argument("--fingerprint", required=True)

    consume = sub.add_parser("consume")
    consume.add_argument("signal_id")
    consume.add_argument("--code", required=True)
    consume.add_argument("--action", required=True)
    consume.add_argument("--at", default=datetime.now().strftime("%Y-%m-%d %H:%M"))

    check = sub.add_parser("check")
    check.add_argument("--direction")
    check.add_argument("--date")
    check.add_argument("--fingerprint")

    args = parser.parse_args()
    payload = load()
    signals = payload["signals"]

    if args.command == "register":
        same = [s for s in signals if s.get("date") == args.date and s.get("fingerprint") == args.fingerprint]
        if same:
            print(json.dumps({"duplicate": True, "signal": same[-1]}, ensure_ascii=False))
            return 2
        prefix = args.kind.upper()
        sequence = 1 + sum(1 for s in signals if s.get("date") == args.date and s.get("kind", "").upper() == prefix)
        digest = hashlib.sha1(args.fingerprint.encode("utf-8")).hexdigest()[:10]
        item = {
            "id": signal_id(prefix, args.date, sequence),
            "direction": args.direction,
            "kind": args.kind,
            "date": args.date,
            "fingerprint": args.fingerprint,
            "fingerprint_hash": digest,
            "status": "pending",
        }
        signals.append(item)
        save(payload)
        print(json.dumps(item, ensure_ascii=False))
        return 0

    if args.command == "consume":
        matches = [s for s in signals if s.get("id") == args.signal_id]
        if not matches:
            raise SystemExit(f"unknown signal: {args.signal_id}")
        item = matches[-1]
        if item.get("status") == "consumed":
            print(json.dumps({"already_consumed": True, "signal": item}, ensure_ascii=False))
            return 2
        item.update({"status": "consumed", "code": args.code, "action": args.action, "consumed_at": args.at})
        save(payload)
        print(json.dumps(item, ensure_ascii=False))
        return 0

    filtered = signals
    if args.direction:
        filtered = [s for s in filtered if s.get("direction") == args.direction]
    if args.date:
        filtered = [s for s in filtered if s.get("date") == args.date]
    if args.fingerprint:
        filtered = [s for s in filtered if s.get("fingerprint") == args.fingerprint]
    print(json.dumps(filtered, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
