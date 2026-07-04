#!/usr/bin/env python3
"""
Analyze trade records against decision logs and indicator snapshots.

This script correlates executed trades with the latest decision JSON
and 15m indicator snapshot prior to the trade timestamp.
"""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

import pandas as pd


DECISION_RE = re.compile(
    r"decision_(?P<symbol>[^_]+)_(?P<date>\d{8})_(?P<time>\d{6})_cycle_(?P<cycle>[^_]+)_(?P<id>\d+)\.json"
)
INDICATOR_RE = re.compile(
    r"indicators_(?P<symbol>[^_]+)_(?P<tf>\d+m|\dh)_(?P<date>\d{8})_(?P<time>\d{6}).*\.csv"
)


def parse_ts(date_str: str, time_str: str) -> datetime:
    return datetime.strptime(f"{date_str}{time_str}", "%Y%m%d%H%M%S")


def build_decision_index(symbols: Iterable[str], root: Path) -> Dict[str, List[Tuple[datetime, Path]]]:
    idx: Dict[str, List[Tuple[datetime, Path]]] = {}
    for symbol in symbols:
        base = root / symbol
        if not base.exists():
            continue
        entries: List[Tuple[datetime, Path]] = []
        for p in base.rglob("decision_*.json"):
            m = DECISION_RE.match(p.name)
            if not m:
                continue
            dt = parse_ts(m.group("date"), m.group("time"))
            entries.append((dt, p))
        entries.sort(key=lambda x: x[0])
        idx[symbol] = entries
    return idx


def build_indicator_index(
    symbols: Iterable[str],
    root: Path,
    timeframe: str = "15m",
) -> Dict[Tuple[str, str], List[Tuple[datetime, Path]]]:
    idx: Dict[Tuple[str, str], List[Tuple[datetime, Path]]] = {}
    for symbol in symbols:
        base = root / symbol
        if not base.exists():
            continue
        entries: List[Tuple[datetime, Path]] = []
        for p in base.rglob("indicators_*.csv"):
            m = INDICATOR_RE.match(p.name)
            if not m:
                continue
            if m.group("tf") != timeframe:
                continue
            dt = parse_ts(m.group("date"), m.group("time"))
            entries.append((dt, p))
        entries.sort(key=lambda x: x[0])
        if entries:
            idx[(symbol, timeframe)] = entries
    return idx


def find_latest(
    entries: List[Tuple[datetime, Path]],
    ts: datetime,
    max_age: timedelta,
) -> Optional[Tuple[datetime, Path]]:
    if not entries:
        return None
    best = None
    for dt, p in entries:
        if dt <= ts:
            best = (dt, p)
        else:
            break
    if best and ts - best[0] <= max_age:
        return best
    return None


def load_decision(path: Path) -> Dict:
    with path.open() as f:
        return json.load(f)


def load_atr_pct(path: Path) -> Optional[float]:
    try:
        df = pd.read_csv(path)
    except Exception:
        return None
    if df.empty or "atr" not in df.columns or "close" not in df.columns:
        return None
    last = df.iloc[-1]
    close = last.get("close")
    atr = last.get("atr")
    if isinstance(close, (int, float)) and isinstance(atr, (int, float)) and close:
        return (atr / close) * 100
    return None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Analyze trade signals vs. decisions and indicators.")
    parser.add_argument("--trades", default="data/execution/trades/all_trades.csv")
    parser.add_argument("--decision-root", default="data/agents/strategy_engine")
    parser.add_argument("--indicator-root", default="data/analytics/indicators")
    parser.add_argument("--max-age-mins", type=int, default=120)
    parser.add_argument("--timeframe", default="15m")
    parser.add_argument("--output-csv", default="")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    trades = pd.read_csv(args.trades)
    trades["record_time"] = pd.to_datetime(trades["record_time"])
    trades = trades[trades["status"] == "CLOSED"].copy()

    symbols = sorted(trades["symbol"].dropna().unique())
    decision_idx = build_decision_index(symbols, Path(args.decision_root))
    indicator_idx = build_indicator_index(symbols, Path(args.indicator_root), args.timeframe)

    rows = []
    max_age = timedelta(minutes=args.max_age_mins)

    for _, tr in trades.iterrows():
        symbol = tr["symbol"]
        ts = tr["record_time"]
        decision_match = find_latest(decision_idx.get(symbol, []), ts, max_age)
        indicator_match = find_latest(indicator_idx.get((symbol, args.timeframe), []), ts, max_age)

        decision = load_decision(decision_match[1]) if decision_match else {}
        position = decision.get("position") or {}
        vote_details = decision.get("vote_details") or {}
        osc_vals = [
            vote_details.get("oscillator_1h"),
            vote_details.get("oscillator_15m"),
            vote_details.get("oscillator_5m"),
        ]
        osc_vals = [v for v in osc_vals if isinstance(v, (int, float))]

        atr_pct = load_atr_pct(indicator_match[1]) if indicator_match else None

        rows.append(
            {
                "symbol": symbol,
                "record_time": ts,
                "action": tr.get("action"),
                "pnl": tr.get("pnl"),
                "confidence": tr.get("confidence"),
                "weighted_score": decision.get("weighted_score"),
                "decision_confidence": decision.get("confidence"),
                "position_pct": position.get("position_pct"),
                "position_location": position.get("location"),
                "osc_min": min(osc_vals) if osc_vals else None,
                "osc_max": max(osc_vals) if osc_vals else None,
                "atr_pct": atr_pct,
            }
        )

    if not rows:
        print("No matching trades found.")
        return

    df = pd.DataFrame(rows)
    matched = df["weighted_score"].notna().sum()
    print(f"Matched trades: {matched}/{len(df)}")
    print(df[[
        "symbol",
        "record_time",
        "action",
        "pnl",
        "position_pct",
        "osc_min",
        "atr_pct",
        "weighted_score",
        "decision_confidence",
    ]].to_string(index=False))

    print("\nPnL by position bucket:")
    df["pos_bucket"] = pd.cut(df["position_pct"], bins=[0, 70, 80, 90, 100], labels=["<=70", "70-80", "80-90", ">90"])
    print(df.groupby("pos_bucket", observed=True)["pnl"].agg(["count", "sum", "mean"]))

    print("\nPnL by oscillator min bucket:")
    df["osc_bucket"] = pd.cut(df["osc_min"], bins=[-100, -40, -20, 0, 100], labels=["<=-40", "-40--20", "-20-0", ">0"])
    print(df.groupby("osc_bucket", observed=True)["pnl"].agg(["count", "sum", "mean"]))

    print("\nPnL by ATR% bucket:")
    df["atr_bucket"] = pd.cut(df["atr_pct"], bins=[0, 0.5, 1.0, 1.5, 2.0, 5.0], labels=["<=0.5", "0.5-1", "1-1.5", "1.5-2", ">2"])
    print(df.groupby("atr_bucket", observed=True)["pnl"].agg(["count", "sum", "mean"]))

    if args.output_csv:
        df.to_csv(args.output_csv, index=False)
        print(f"\nSaved: {args.output_csv}")


if __name__ == "__main__":
    main()
