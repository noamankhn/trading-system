"""
Shared performance analysis: backtest, walk-forward, and live P&L computation.
Used by dashboard/app.py AND improvement/analyzer.py - kept in one place so both always
agree on the numbers (a lesson learned from an earlier bug where dashboard and paper_trader
had two separate copies of symbol-normalization logic that drifted out of sync).
"""

import sys
import os
import time

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
from strategies.signals import STRATEGIES

_strategy_perf_cache = {}
_CACHE_TTL_SECONDS = 6 * 60 * 60  # 6 hours


def compute_backtest_and_walkforward(symbol, use_cache=True):
    """
    Full-period backtest + walk-forward consistency stats for one symbol.
    Cached for 6 hours since it's based on historical data that only changes daily.
    """
    now = time.time()
    if use_cache:
        cached = _strategy_perf_cache.get(symbol)
        if cached and (now - cached["ts"]) < _CACHE_TTL_SECONDS:
            return cached["data"]

    from data.fetcher import fetch_historical
    from backtest.engine import run_backtest
    import walk_forward as wf

    strategy_name = config.STRATEGY_MAP.get(symbol, config.STRATEGY)
    strategy_fn = STRATEGIES[strategy_name]

    df = fetch_historical(symbol, config.BACKTEST_START, config.BACKTEST_END)

    if strategy_name == "sma_crossover":
        df_signaled = strategy_fn(df.copy(), config.FAST_MA, config.SLOW_MA)
    else:
        df_signaled = strategy_fn(df.copy(), config.RSI_PERIOD, config.RSI_OVERSOLD, config.RSI_OVERBOUGHT)
    backtest_metrics = run_backtest(df_signaled, config, commission_pct=config.COMMISSION_PCT)["metrics"]

    windows = wf.make_windows(df)
    wf_metrics_list = []
    for test_start, test_end in windows:
        window_df = df[(df.index >= test_start) & (df.index < test_end)].copy()
        if len(window_df) < 30:
            continue
        if strategy_name == "sma_crossover":
            window_df = strategy_fn(window_df, config.FAST_MA, config.SLOW_MA)
        else:
            window_df = strategy_fn(window_df, config.RSI_PERIOD, config.RSI_OVERSOLD, config.RSI_OVERBOUGHT)
        wf_metrics_list.append(run_backtest(window_df, config, commission_pct=config.COMMISSION_PCT)["metrics"])

    profitable = sum(1 for m in wf_metrics_list
                      if isinstance(m.get("total_return_pct"), (int, float)) and m["total_return_pct"] > 0)
    total_windows = len(wf_metrics_list)
    sharpes = [m["sharpe_ratio"] for m in wf_metrics_list if isinstance(m.get("sharpe_ratio"), (int, float))]
    avg_sharpe = round(sum(sharpes) / len(sharpes), 2) if sharpes else None

    data = {
        "strategy": strategy_name,
        "backtest": {
            "return_pct": backtest_metrics["total_return_pct"],
            "sharpe": backtest_metrics["sharpe_ratio"],
            "win_rate_pct": backtest_metrics["win_rate_pct"],
            "profit_factor": backtest_metrics["profit_factor"],
        },
        "walk_forward": {
            "profitable_windows": profitable,
            "total_windows": total_windows,
            "avg_sharpe": avg_sharpe,
        },
    }
    _strategy_perf_cache[symbol] = {"data": data, "ts": now}
    return data


def compute_cumulative_performance(client, open_positions):
    """
    Realized + unrealized P&L since this system started trading, using Alpaca's actual
    filled order history (average-cost method per symbol). Includes a per-symbol breakdown.
    """
    from alpaca.trading.requests import GetOrdersRequest
    from alpaca.trading.enums import QueryOrderStatus

    request = GetOrdersRequest(status=QueryOrderStatus.CLOSED, limit=500)
    closed_orders = client.get_orders(request)

    filled = [o for o in closed_orders if o.filled_qty and float(o.filled_qty) > 0
              and o.filled_avg_price is not None]
    filled.sort(key=lambda o: o.filled_at or o.submitted_at)

    cost_basis = {}
    realized_pnl = 0.0
    realized_pnl_by_symbol = {}

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
            realized_pnl += trade_pnl
            realized_pnl_by_symbol[symbol] = realized_pnl_by_symbol.get(symbol, 0.0) + trade_pnl
            remaining = cur_qty - sell_qty
            cost_basis[symbol] = (remaining, cur_avg if remaining > 0 else 0.0)

    unrealized_pnl = sum(p["unrealized_pl"] for p in open_positions)
    unrealized_by_symbol = {config.normalize_alpaca_symbol(p["symbol"]): p["unrealized_pl"]
                             for p in open_positions}

    all_symbols = set(realized_pnl_by_symbol) | set(unrealized_by_symbol)
    by_symbol = {
        sym: {
            "realized": realized_pnl_by_symbol.get(sym, 0.0),
            "unrealized": unrealized_by_symbol.get(sym, 0.0),
            "total": realized_pnl_by_symbol.get(sym, 0.0) + unrealized_by_symbol.get(sym, 0.0),
        }
        for sym in all_symbols
    }

    total_pnl = realized_pnl + unrealized_pnl
    total_return_pct = (total_pnl / config.STARTING_CAPITAL) * 100 if config.STARTING_CAPITAL else 0

    return {
        "realized_pnl": realized_pnl,
        "unrealized_pnl": unrealized_pnl,
        "total_pnl": total_pnl,
        "total_return_pct": total_return_pct,
        "closed_trades_counted": len(filled),
        "by_symbol": by_symbol,
    }
