"""
Self-improvement analyzer: compares live paper trading results against backtest and
walk-forward expectations, and generates SPECIFIC, BOUNDED proposals for human review.

This deliberately does NOT generate or modify code. Every proposal is one of a small,
fixed set of safe change types (see PROPOSAL_TYPES below), applied only to
tunable_config.json after a human sets "approved": true on that specific proposal.

Usage:
    python improvement/analyzer.py
"""

import sys
import os
import json
from datetime import datetime, timezone

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
from analysis.performance import compute_backtest_and_walkforward, compute_cumulative_performance

PROPOSALS_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                               "improvement_proposals.json")

# The ONLY kinds of changes this system is allowed to propose. Anything not on this list
# cannot be generated, regardless of what an LLM "suggests" during the council review step.
PROPOSAL_TYPES = {"demote_to_watchlist", "promote_to_active", "adjust_risk_parameter"}


def _get_live_client():
    from alpaca.trading.client import TradingClient
    return TradingClient(config.ALPACA_API_KEY, config.ALPACA_SECRET_KEY, paper=True)


def _get_open_positions(client):
    raw = client.get_all_positions()
    return [{
        "symbol": p.symbol,
        "unrealized_pl": float(p.unrealized_pl),
    } for p in raw]


def generate_findings():
    """
    Returns a list of specific, bounded proposals based on comparing walk-forward evidence
    (the most reliable signal we have) against what's currently active/watchlisted.
    """
    client = _get_live_client()
    positions = _get_open_positions(client)
    live_perf = compute_cumulative_performance(client, positions)

    findings = []

    # Check active symbols for demotion candidates: walk-forward evidence has weakened
    for symbol in config.ACTIVE_SYMBOLS:
        try:
            bt_wf = compute_backtest_and_walkforward(symbol, use_cache=False)
        except Exception as e:
            findings.append({
                "type": "data_error", "symbol": symbol,
                "reason": f"Could not compute backtest/walk-forward: {e}",
                "approved": False,
            })
            continue

        wf = bt_wf["walk_forward"]
        live = live_perf["by_symbol"].get(symbol, {"realized": 0.0, "unrealized": 0.0, "total": 0.0})

        if wf["total_windows"] > 0 and wf["profitable_windows"] / wf["total_windows"] < 0.5:
            findings.append({
                "type": "demote_to_watchlist",
                "symbol": symbol,
                "reason": (f"Walk-forward shows only {wf['profitable_windows']}/{wf['total_windows']} "
                           f"profitable windows (avg Sharpe {wf['avg_sharpe']}) - below the 50% "
                           f"consistency bar. Live P&L so far: ${live['total']:.2f}"),
                "proposed_change": f"Move {symbol} from active_symbols to watchlist_symbols",
                "approved": False,
            })

    # Check watchlist symbols for promotion candidates: strong walk-forward evidence emerged
    for symbol in config.WATCHLIST_SYMBOLS:
        try:
            bt_wf = compute_backtest_and_walkforward(symbol, use_cache=False)
        except Exception as e:
            continue

        wf = bt_wf["walk_forward"]
        if (wf["total_windows"] > 0 and wf["profitable_windows"] / wf["total_windows"] >= 0.75
                and isinstance(wf["avg_sharpe"], (int, float)) and wf["avg_sharpe"] > 0.5):
            findings.append({
                "type": "promote_to_active",
                "symbol": symbol,
                "reason": (f"Walk-forward now shows {wf['profitable_windows']}/{wf['total_windows']} "
                           f"profitable windows with avg Sharpe {wf['avg_sharpe']} - meets the bar "
                           f"that SPY/GLD/BTC-USD were originally selected on."),
                "proposed_change": f"Move {symbol} from watchlist_symbols to active_symbols",
                "approved": False,
            })

    return findings


def write_proposals(findings):
    existing = {"proposals": []}
    if os.path.exists(PROPOSALS_PATH):
        try:
            with open(PROPOSALS_PATH) as f:
                existing = json.load(f)
        except json.JSONDecodeError:
            pass

    existing_keys = {(p.get("type"), p.get("symbol")) for p in existing.get("proposals", [])
                      if not p.get("applied")}

    new_count = 0
    for finding in findings:
        key = (finding.get("type"), finding.get("symbol"))
        if key not in existing_keys:
            finding["id"] = len(existing.get("proposals", [])) + 1
            finding["generated_at"] = datetime.now(timezone.utc).isoformat()
            finding["applied"] = False
            existing.setdefault("proposals", []).append(finding)
            new_count += 1

    existing["last_run_at"] = datetime.now(timezone.utc).isoformat()

    with open(PROPOSALS_PATH, "w") as f:
        json.dump(existing, f, indent=2)

    print(f"Wrote {new_count} new proposal(s) to {PROPOSALS_PATH}")
    print(f"Total pending (unapplied) proposals: "
          f"{sum(1 for p in existing['proposals'] if not p.get('applied'))}")
    return existing


if __name__ == "__main__":
    findings = generate_findings()
    if not findings:
        print("No new findings this run - current setup still matches the evidence.")
    else:
        for f in findings:
            print(f"\n[{f['type']}] {f.get('symbol', '')}")
            print(f"  Reason: {f['reason']}")
        write_proposals(findings)
