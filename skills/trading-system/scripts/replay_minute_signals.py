#!/usr/bin/env python3
"""Replay minute bars and emit both direction and direction-free market signals."""

import argparse
import json
import os
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
ASTOCK = os.environ.get("ASTOCK_BIN", str(ROOT / "astock" / "astock"))
MAIN_BOARD_PREFIXES = ("000", "001", "002", "600", "601", "603", "605")


def astock_json(*args):
    result = subprocess.run(
        [ASTOCK, *args, "--json"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as error:
        raise RuntimeError(f"astock returned non-JSON for: {' '.join(args)}") from error


def load_stock(code, date):
    daily = astock_json(
        "query", "kline", code, "--freq", "daily", "--from", date, "--to", date
    )
    try:
        minute = astock_json(
            "query", "kline", code, "--freq", "1m", "--date", date, "--no-sync"
        )
    except RuntimeError:
        subprocess.run(
            [ASTOCK, "sync", "kline", "--code", code, "--freq", "1m"],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
        minute = astock_json(
            "query", "kline", code, "--freq", "1m", "--date", date, "--no-sync"
        )
    if not daily or len(minute) != 240:
        raise RuntimeError(f"{code}: expected one daily bar and 240 minute bars")
    pre_close = float(daily[0]["pre_close"])
    return pre_close, {row["time"][-5:]: row for row in minute}


def limit_threshold(code):
    return 19.8 if code.startswith(("300", "301", "688")) else 9.8


def is_main_board(code):
    return code.startswith(MAIN_BOARD_PREFIXES)


def dedupe_by_code(rows):
    """Defend the signal layer from duplicate rows in upstream snapshots."""
    result = {}
    for row in rows:
        code = row.get("code")
        if code and code not in result:
            result[code] = row
    return result


def build_market_candidates(limit_rows, amount_rows):
    """Build a label-independent preload universe; this does not declare leaders."""
    candidates = {}
    for source, rows in (("limit", limit_rows), ("amount", amount_rows)):
        for code, row in dedupe_by_code(rows).items():
            name = row.get("name", "")
            if not is_main_board(code) or "ST" in name.upper():
                continue
            item = candidates.setdefault(
                code,
                {
                    "code": code,
                    "name": name,
                    "industry": row.get("industry", ""),
                    "sector": row.get("sector", ""),
                    "business": row.get("business", ""),
                    "sources": [],
                },
            )
            if source not in item["sources"]:
                item["sources"].append(source)
            for field in ("name", "industry", "sector", "business"):
                if not item.get(field) and row.get(field):
                    item[field] = row[field]
    return candidates


def candidate_events(code, pct_history, cumulative_amount, min_amount):
    """Return attention events only; events trigger attribution, never a buy."""
    current = pct_history[-1]
    acceleration_10m = 0.0
    if len(pct_history) >= 11:
        acceleration_10m = current - pct_history[-11]
    rebound = current - min(pct_history)
    events = []
    if cumulative_amount >= min_amount:
        if len(pct_history) >= 11 and current >= 7 and acceleration_10m >= 3:
            events.append(("10m_acceleration", acceleration_10m, rebound))
        if current >= 3 and rebound >= 8:
            events.append(("deep_reversal", acceleration_10m, rebound))
        if current >= limit_threshold(code):
            events.append(("first_limit", acceleration_10m, rebound))
    return events


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", required=True, help="YYYYMMDD")
    parser.add_argument("--group", action="append", default=[], help="name=code,code")
    parser.add_argument("--block", action="append", default=[], help="name=block_code")
    parser.add_argument("--holding", action="append", default=[], help="code")
    parser.add_argument(
        "--no-market-candidates",
        action="store_true",
        help="disable the independent main-board candidate detector",
    )
    parser.add_argument(
        "--top-amount",
        type=int,
        default=50,
        help="preload this many daily turnover leaders (default: 50)",
    )
    parser.add_argument(
        "--candidate-min-amount",
        type=float,
        default=1_000_000_000,
        help="minimum as-of-minute cumulative amount for candidate events",
    )
    args = parser.parse_args()

    groups = {}
    for raw in args.group:
        name, codes = raw.split("=", 1)
        groups[name] = codes.split(",")
    limit_rows = astock_json("query", "limit", args.date, "--exclude-st")
    if args.block:
        limit_codes = set(dedupe_by_code(limit_rows))
        for raw in args.block:
            name, block_code = raw.split("=", 1)
            members = astock_json("query", "block", "members", block_code, args.date)
            groups[name] = sorted({row["code"] for row in members} & limit_codes)

    market_candidates = {}
    if not args.no_market_candidates:
        amount_rows = astock_json(
            "query",
            "stock",
            "--date",
            args.date,
            "--sort-by",
            "amount",
            "--limit",
            str(args.top_amount),
        )
        market_candidates = build_market_candidates(limit_rows, amount_rows)

    required_codes = set(args.holding).union(*map(set, groups.values()))
    all_codes = sorted(required_codes | set(market_candidates))
    stocks = {}
    missing_candidates = []
    for code in all_codes:
        try:
            stocks[code] = load_stock(code, args.date)
        except (RuntimeError, subprocess.CalledProcessError):
            if code in required_codes:
                raise
            missing_candidates.append(code)
    if not stocks:
        raise RuntimeError("no minute series loaded")

    for name, codes in groups.items():
        groups[name] = [code for code in codes if code in stocks]
    market_candidates = {
        code: item for code, item in market_candidates.items() if code in stocks
    }
    times = sorted(next(iter(stocks.values()))[1])
    previous = {}
    candidate_history = {code: [] for code in market_candidates}
    candidate_amount = {code: 0.0 for code in market_candidates}
    emitted_candidate_events = set()
    scanned = 0

    for time in times:
        scanned += 1
        changes = []
        for code, item in market_candidates.items():
            pre_close, minute = stocks[code]
            row = minute[time]
            close = float(row["close"])
            pct = (close / pre_close - 1) * 100
            candidate_history[code].append(pct)
            candidate_amount[code] += float(row.get("amount", 0))
            for event, acceleration, rebound in candidate_events(
                code,
                candidate_history[code],
                candidate_amount[code],
                args.candidate_min_amount,
            ):
                event_key = (code, event)
                if event_key in emitted_candidate_events:
                    continue
                emitted_candidate_events.add(event_key)
                business = item.get("business") or "unknown"
                changes.append(
                    "CANDIDATE "
                    f"{code} {item.get('name', '')} {event} pct={pct:+.2f}% "
                    f"amount={candidate_amount[code] / 1e8:.1f}e8 "
                    f"accel10m={acceleration:+.2f}pp rebound={rebound:+.2f}pp "
                    f"business={business} -> search_expectation_and_check_related_stocks"
                )

        for name, codes in groups.items():
            if not codes:
                continue
            rows = []
            for code in codes:
                pre_close, minute = stocks[code]
                close = float(minute[time]["close"])
                pct = (close / pre_close - 1) * 100
                rows.append((code, pct, close))
            rows.sort(key=lambda row: row[1], reverse=True)
            state = (
                sum(row[1] >= 5 for row in rows),
                sum(row[1] >= limit_threshold(row[0]) for row in rows),
                rows[0][0],
            )
            if state != previous.get(name):
                leader = rows[0]
                changes.append(
                    f"{name}: >=5% {state[0]}/{len(rows)}, limit {state[1]}, "
                    f"leader {leader[0]} {leader[1]:+.2f}%@{leader[2]:.2f}"
                )
                previous[name] = state

        for code in args.holding:
            pre_close, minute = stocks[code]
            close = float(minute[time]["close"])
            pct = (close / pre_close - 1) * 100
            band = int(abs(pct) // 2) * (1 if pct >= 0 else -1)
            key = f"holding:{code}"
            if band != previous.get(key):
                changes.append(f"holding {code}: {pct:+.2f}%@{close:.2f} (2% band {band:+d})")
                previous[key] = band

        if changes:
            print(f"{time} | " + " | ".join(changes))

    print(
        "COVERAGE_MODE=candidate_universe "
        "(final limits + daily top turnover; not full-market minute coverage)"
    )
    print(f"SCANNED_SYMBOLS={len(stocks)}")
    print(f"MARKET_CANDIDATES={len(market_candidates)}")
    print(f"MISSING_CANDIDATES={','.join(missing_candidates) or 'none'}")
    print(f"CANDIDATE_EVENTS={len(emitted_candidate_events)}")
    print(f"SCANNED_MINUTES={scanned}")


if __name__ == "__main__":
    main()
