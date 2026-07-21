"""
Calibration check: compares LIVE trade-level results (actual win rate, actual trade sizes)
against what the backtest/walk-forward predicted, for each actively-traded symbol.

This answers a different question than the demote/promote findings do:
  - demote/promote: "does the historical evidence still support trading this symbol?"
  - calibration: "is what's actually happening live still matching what we expected,
    right now, with real trades?"

Calibration findings are informational only - "calibration_drift" is not in
improvement/analyzer.py's PROPOSAL_TYPES and apply_approved.py will never act on it
automatically (unknown proposal types are always skipped, by design). It exists so you
see drift early, before it's severe enough to also show up as a demote_to_watchlist finding.

Runs as part of every improvement/analyzer.py cycle - not a separate schedule.
"""

import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
from analysis.performance import compute_backtest_and_walkforward

MIN_TRADES_FOR_CALIBRATION = 5  # below this, live sample is too small to judge - skip, don't guess
WIN_RATE_DRIFT_THRESHOLD_PP = 20  # percentage points of divergence considered "significant"


def compute_live_trade_pnls(client):
    """
    Returns {symbol: [individual realized trade P&L, ...]} using the same average-cost
    method as analysis/performance.py, but keeping each trade's result separately instead
    of only the sum - needed to compute a live win rate, not just total P&L.
    """
    from alpaca.trading.requests import GetOrdersRequest
    from alpaca.trading.enums import QueryOrderStatus

    request = GetOrdersRequest(status=QueryOrderStatus.CLOSED, limit=500)
    closed_orders = client.get_orders(request)
    filled = [o for o in closed_orders if o.filled_qty and float(o.filled_qty) > 0
              and o.filled_avg_price is not None]
    filled.sort(key=lambda o: o.filled_at or o.submitted_at)

    cost_basis = {}
    trades_by_symbol = {}

    for o in filled:
        symbol = config.normalize_alpaca_symbol(o.symbol)
        qty = float(o.filled_qty)
        price = float(o.filled_avg_price)
        side = o.side.value if hasattr(o.side, "value") else str(o.side)
        cur_qty, cur_avg = cost_basis.get(symbol, (0.0, 0.0))

        if side == "buy":
            new_qty = cur_qty + qty
            new_avg = (cur_qty * cur_avg + qty * price) / new_qty if new_qty > 0 else 0.0
            cost_basis[symbol] = (new_qty, new_avg)
        else:
            sell_qty = min(qty, cur_qty) if cur_qty > 0 else 0.0
            trade_pnl = sell_qty * (price - cur_avg)
            trades_by_symbol.setdefault(symbol, []).append(trade_pnl)
            remaining = cur_qty - sell_qty
            cost_basis[symbol] = (remaining, cur_avg if remaining > 0 else 0.0)

    return trades_by_symbol


def compute_calibration_findings(client):
    """
    Returns a list of calibration_drift findings for active symbols with enough live
    trades to judge, where live win rate has drifted significantly from what the
    backtest predicted.
    """
    trades_by_symbol = compute_live_trade_pnls(client)
    findings = []

    for symbol in config.ACTIVE_SYMBOLS:
        trades = trades_by_symbol.get(symbol, [])
        if len(trades) < MIN_TRADES_FOR_CALIBRATION:
            continue  # not enough live trades yet - don't guess from a tiny sample

        wins = [t for t in trades if t > 0]
        live_win_rate = (len(wins) / len(trades)) * 100

        try:
            bt_wf = compute_backtest_and_walkforward(symbol, use_cache=True)
        except Exception:
            continue

        expected_win_rate = bt_wf["backtest"]["win_rate_pct"]
        if not isinstance(expected_win_rate, (int, float)):
            continue

        drift = live_win_rate - expected_win_rate

        if abs(drift) >= WIN_RATE_DRIFT_THRESHOLD_PP:
            findings.append({
                "type": "calibration_drift",  # informational only - never auto-applied
                "symbol": symbol,
                "reason": (
                    f"Live win rate ({live_win_rate:.1f}% over {len(trades)} real trades) has "
                    f"drifted {drift:+.1f} percentage points from the backtest-predicted win rate "
                    f"({expected_win_rate:.1f}%). This may mean current market conditions differ "
                    f"from the backtested period, or it may just be small-sample noise - worth "
                    f"watching, not necessarily acting on yet."
                ),
                "live_win_rate": round(live_win_rate, 1),
                "expected_win_rate": expected_win_rate,
                "sample_size": len(trades),
                "approved": False,  # calibration findings inform, they don't get "approved into" a change
            })

    return findings
