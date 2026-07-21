"""
Reconstructs individual closed trades (full buy -> sell holding periods) from Alpaca order
history, then analyzes each trade's actual daily price path between entry and exit to answer:
"did this position ever go into profit before it closed, and did it exit via take-profit,
stop-loss, or a signal flip?"

This is what makes closed-trade analysis meaningful rather than just "won $12, lost $8" -
it shows the PATH each trade took, not just the destination.
"""

import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config

# Small tolerance for matching an exit price to the configured TP/SL % - live fills can differ
# slightly from the exact daily close price the decision was made on (next-session execution).
EXIT_REASON_TOLERANCE = 0.01  # 1 percentage point


def reconstruct_closed_trades(client, max_trades=25):
    """
    Walks filled order history chronologically per symbol, tracking holding periods.
    A "trade" = the full period from when a position opens from flat to when it returns
    to flat (handles partial buys/sells within that period using average cost).
    Returns the most recent `max_trades` closed trades across all symbols, newest first.
    """
    from alpaca.trading.requests import GetOrdersRequest
    from alpaca.trading.enums import QueryOrderStatus

    request = GetOrdersRequest(status=QueryOrderStatus.CLOSED, limit=500)
    closed_orders = client.get_orders(request)
    filled = [o for o in closed_orders if o.filled_qty and float(o.filled_qty) > 0
              and o.filled_avg_price is not None]
    filled.sort(key=lambda o: o.filled_at or o.submitted_at)

    state = {}  # symbol -> {"qty": float, "avg_price": float, "entry_date": datetime}
    trades = []

    for o in filled:
        symbol = config.normalize_alpaca_symbol(o.symbol)
        qty = float(o.filled_qty)
        price = float(o.filled_avg_price)
        side = o.side.value if hasattr(o.side, "value") else str(o.side)
        fill_time = o.filled_at or o.submitted_at

        cur = state.get(symbol, {"qty": 0.0, "avg_price": 0.0, "entry_date": None})

        if side == "buy":
            new_qty = cur["qty"] + qty
            new_avg = (cur["qty"] * cur["avg_price"] + qty * price) / new_qty if new_qty > 0 else 0.0
            entry_date = cur["entry_date"] if cur["qty"] > 0 else fill_time  # keep original entry if adding
            state[symbol] = {"qty": new_qty, "avg_price": new_avg, "entry_date": entry_date}
        else:  # sell
            sell_qty = min(qty, cur["qty"]) if cur["qty"] > 0 else 0.0
            if sell_qty > 0:
                pnl_dollars = sell_qty * (price - cur["avg_price"])
                pnl_pct = (price - cur["avg_price"]) / cur["avg_price"] if cur["avg_price"] else 0.0
                remaining = cur["qty"] - sell_qty

                if remaining <= 1e-9:  # position fully closed - this is a complete trade
                    trades.append({
                        "symbol": symbol,
                        "entry_date": cur["entry_date"],
                        "entry_price": cur["avg_price"],
                        "exit_date": fill_time,
                        "exit_price": price,
                        "qty": sell_qty,
                        "pnl_dollars": pnl_dollars,
                        "pnl_pct": pnl_pct * 100,
                    })
                    state[symbol] = {"qty": 0.0, "avg_price": 0.0, "entry_date": None}
                else:
                    state[symbol] = {"qty": remaining, "avg_price": cur["avg_price"],
                                      "entry_date": cur["entry_date"]}

    trades.sort(key=lambda t: t["exit_date"], reverse=True)
    return trades[:max_trades]


def analyze_trade_path(trade):
    """
    Fetches the daily price path between a trade's entry and exit dates, computes the
    running unrealized P&L to find the max favorable excursion (best point reached) and
    max adverse excursion (worst point reached), and infers the likely exit reason.
    """
    from data.fetcher import fetch_historical

    symbol = trade["symbol"]
    entry_date = trade["entry_date"]
    exit_date = trade["exit_date"]
    entry_price = trade["entry_price"]

    start_str = entry_date.strftime("%Y-%m-%d")
    end_str = (exit_date).strftime("%Y-%m-%d")

    try:
        df = fetch_historical(symbol, start_str, end_str)
    except Exception as e:
        return {
            "mfe_pct": None, "mae_pct": None, "exit_reason": _infer_exit_reason(trade),
            "path_error": str(e),
        }

    if df.empty or entry_price == 0:
        return {"mfe_pct": None, "mae_pct": None, "exit_reason": _infer_exit_reason(trade),
                "path_error": "No price path data available"}

    daily_pct = ((df["Close"] - entry_price) / entry_price) * 100
    mfe_pct = float(daily_pct.max())  # best it ever looked, on paper
    mae_pct = float(daily_pct.min())  # worst it ever looked, on paper

    return {
        "mfe_pct": round(mfe_pct, 2),
        "mae_pct": round(mae_pct, 2),
        "exit_reason": _infer_exit_reason(trade),
        "path_error": None,
    }


def _infer_exit_reason(trade):
    """
    Infers whether a trade likely exited via take-profit, stop-loss, or a signal flip,
    by comparing the actual exit % against the configured TP/SL thresholds with a small
    tolerance for execution slippage.
    """
    pnl_pct = trade["pnl_pct"] / 100
    tp_target = config.TAKE_PROFIT_PCT
    sl_target = -config.STOP_LOSS_PCT

    if pnl_pct >= tp_target - EXIT_REASON_TOLERANCE:
        return "TAKE_PROFIT"
    elif pnl_pct <= sl_target + EXIT_REASON_TOLERANCE:
        return "STOP_LOSS"
    else:
        return "SIGNAL_FLIP"


def get_closed_trades_with_analysis(client, max_trades=25):
    """Full pipeline: reconstruct trades, then analyze each one's price path."""
    trades = reconstruct_closed_trades(client, max_trades=max_trades)
    for trade in trades:
        analysis = analyze_trade_path(trade)
        trade.update(analysis)
    return trades
