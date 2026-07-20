"""
Private live dashboard for the paper trading system.
Shows account equity, risk parameters, data sources, open positions (expandable with
strategy + indicator detail), and recent orders - pulled live from Alpaca + yfinance.
Protected by a username/password so only you can see it.

Run locally to test:
    pip install flask
    set DASHBOARD_USERNAME=youruser
    set DASHBOARD_PASSWORD=yourpassword
    python dashboard/app.py
Then open http://localhost:5000

On Render, this becomes a free Web Service (see render.yaml) - Render gives it a public
URL, but the login screen means only someone with your username/password can see anything.
"""

import sys
import os
from functools import wraps
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flask import Flask, request, Response, render_template_string
import config
from strategies.signals import STRATEGIES
from analysis.performance import compute_cumulative_performance, compute_backtest_and_walkforward

app = Flask(__name__)

DASHBOARD_USERNAME = os.environ.get("DASHBOARD_USERNAME", "")
DASHBOARD_PASSWORD = os.environ.get("DASHBOARD_PASSWORD", "")


def check_auth(username, password):
    return username == DASHBOARD_USERNAME and password == DASHBOARD_PASSWORD


def authenticate():
    return Response(
        "Login required.", 401,
        {"WWW-Authenticate": 'Basic realm="Trading Dashboard"'}
    )


def requires_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not DASHBOARD_USERNAME or not DASHBOARD_PASSWORD:
            return Response(
                "DASHBOARD_USERNAME and DASHBOARD_PASSWORD environment variables "
                "are not set - refusing to serve an unprotected dashboard.", 500
            )
        auth = request.authorization
        if not auth or not check_auth(auth.username, auth.password):
            return authenticate()
        return f(*args, **kwargs)
    return decorated



def get_indicator_snapshot(symbol):
    """
    Fetches recent data and computes the current strategy/indicator state for one symbol -
    what the system is actually looking at right now to decide long/flat.
    """
    from data.fetcher import fetch_recent

    strategy_name = config.STRATEGY_MAP.get(symbol, config.STRATEGY)
    strategy_fn = STRATEGIES[strategy_name]

    df = fetch_recent(symbol, lookback_days=90)
    if df.empty or len(df) == 0:
        raise ValueError(f"No price data returned for symbol '{symbol}' - check the symbol format is valid")

    if strategy_name == "sma_crossover":
        df = strategy_fn(df, config.FAST_MA, config.SLOW_MA)
        latest = df.iloc[-1]
        indicators = {
            f"Fast MA ({config.FAST_MA})": round(float(latest["fast_ma"]), 2),
            f"Slow MA ({config.SLOW_MA})": round(float(latest["slow_ma"]), 2),
        }
    else:
        df = strategy_fn(df, config.RSI_PERIOD, config.RSI_OVERSOLD, config.RSI_OVERBOUGHT)
        latest = df.iloc[-1]
        indicators = {
            f"RSI ({config.RSI_PERIOD})": round(float(latest["rsi"]), 2),
            "Oversold threshold": config.RSI_OVERSOLD,
            "Overbought threshold": config.RSI_OVERBOUGHT,
        }

    return {
        "strategy": strategy_name,
        "signal": "LONG" if latest["signal"] == 1 else "FLAT",
        "close": round(float(latest["Close"]), 2),
        "as_of": df.index[-1].strftime("%Y-%m-%d"),
        "indicators": indicators,
    }


PAGE_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>Trading Dashboard</title>
    <meta http-equiv="refresh" content="300">
    <style>
        body { font-family: -apple-system, sans-serif; background: #0f172a; color: #e2e8f0;
               max-width: 900px; margin: 40px auto; padding: 0 20px; }
        h1 { color: #f8fafc; }
        .card { background: #1e293b; border-radius: 10px; padding: 20px; margin-bottom: 20px; }
        .label { color: #94a3b8; font-size: 13px; text-transform: uppercase; }
        .value { font-size: 28px; font-weight: 600; margin-top: 4px; }
        .positive { color: #4ade80; }
        .negative { color: #f87171; }
        table { width: 100%; border-collapse: collapse; margin-top: 10px; }
        th, td { text-align: left; padding: 8px; border-bottom: 1px solid #334155; font-size: 14px; }
        th { color: #94a3b8; font-weight: 500; }
        .empty { color: #64748b; padding: 20px; text-align: center; }
        .risk-note { color: #94a3b8; font-size: 12px; margin-top: 10px; }
        .error { color: #f87171; background: #1e293b; padding: 15px; border-radius: 8px; }
        .risk-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; margin-top: 10px; }
        .risk-item { background: #0f172a; border-radius: 8px; padding: 10px 14px; }
        .risk-item .rlabel { color: #94a3b8; font-size: 12px; }
        .risk-item .rvalue { font-size: 18px; font-weight: 600; color: #f8fafc; }
        details { background: #0f172a; border-radius: 8px; margin-bottom: 8px; overflow: hidden; }
        summary { padding: 12px 14px; cursor: pointer; list-style: none; display: flex;
                  justify-content: space-between; align-items: center; }
        summary::-webkit-details-marker { display: none; }
        summary .sym { font-weight: 600; color: #f8fafc; }
        .unmanaged-badge { background: #7c2d12; color: #fdba74; font-size: 11px;
                            padding: 2px 6px; border-radius: 4px; margin-left: 8px; font-weight: 600; }
        .sp-table { width: 100%; border-collapse: collapse; margin-top: 10px; }
        .sp-table th { text-align: left; padding: 8px; font-size: 11px; text-transform: uppercase;
                        color: #94a3b8; border-bottom: 1px solid #334155; }
        .sp-table td { padding: 10px 8px; font-size: 13px; border-bottom: 1px solid #1e293b; vertical-align: top; }
        .sp-symbol { font-weight: 600; color: #f8fafc; }
        .sp-strategy { color: #94a3b8; font-size: 12px; }
        .sp-stage-label { color: #64748b; font-size: 10px; text-transform: uppercase; display: block; }
        summary::after { content: "▸"; color: #64748b; transition: transform 0.15s; }
        details[open] summary::after { transform: rotate(90deg); }
        .detail-body { padding: 0 14px 14px 14px; border-top: 1px solid #1e293b; }
        .indicator-row { display: flex; justify-content: space-between; padding: 4px 0;
                          font-size: 13px; color: #cbd5e1; }
        .signal-badge { padding: 2px 8px; border-radius: 4px; font-size: 12px; font-weight: 600; }
        .signal-long { background: #14532d; color: #4ade80; }
        .signal-flat { background: #334155; color: #94a3b8; }
        .source-item { font-size: 13px; color: #cbd5e1; padding: 6px 0; border-bottom: 1px solid #334155; }
        .source-item:last-child { border-bottom: none; }
        .perf-banner { display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; }
        .perf-item { text-align: center; }
        .perf-item .plabel { color: #94a3b8; font-size: 12px; text-transform: uppercase; }
        .perf-item .pvalue { font-size: 22px; font-weight: 700; margin-top: 4px; }
        .position-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 6px 16px; margin-top: 6px; }
        .pos-field { display: flex; justify-content: space-between; font-size: 13px;
                     padding: 5px 0; border-bottom: 1px solid #1e293b; }
        .pos-field .pflabel { color: #94a3b8; }
        .pos-field .pfvalue { color: #f8fafc; font-weight: 500; }
        .tp-value { color: #4ade80; }
        .sl-value { color: #f87171; }
        .liq-note { color: #64748b; font-style: italic; }
    </style>
</head>
<body>
    <h1>Paper Trading Dashboard</h1>
    {% if error %}
        <div class="error">Could not load Alpaca data: {{ error }}</div>
    {% else %}
    <div class="card">
        <div class="label">Cumulative Performance (since this system started trading)</div>
        <div class="perf-banner" style="margin-top: 12px;">
            <div class="perf-item">
                <div class="plabel">Realized P&amp;L</div>
                <div class="pvalue {{ 'positive' if perf.realized_pnl >= 0 else 'negative' }}">
                    {{ "+" if perf.realized_pnl >= 0 else "" }}${{ "%.2f"|format(perf.realized_pnl) }}</div>
            </div>
            <div class="perf-item">
                <div class="plabel">Unrealized P&amp;L</div>
                <div class="pvalue {{ 'positive' if perf.unrealized_pnl >= 0 else 'negative' }}">
                    {{ "+" if perf.unrealized_pnl >= 0 else "" }}${{ "%.2f"|format(perf.unrealized_pnl) }}</div>
            </div>
            <div class="perf-item">
                <div class="plabel">Total P&amp;L</div>
                <div class="pvalue {{ 'positive' if perf.total_pnl >= 0 else 'negative' }}">
                    {{ "+" if perf.total_pnl >= 0 else "" }}${{ "%.2f"|format(perf.total_pnl) }}</div>
            </div>
            <div class="perf-item">
                <div class="plabel">Total Return</div>
                <div class="pvalue {{ 'positive' if perf.total_return_pct >= 0 else 'negative' }}">
                    {{ "+" if perf.total_return_pct >= 0 else "" }}{{ "%.2f"|format(perf.total_return_pct) }}%</div>
            </div>
        </div>
        <div class="risk-note">Based on {{ perf.closed_trades_counted }} closed order(s) + {{ positions|length }} open position(s), vs. your ${{ starting_capital }} tracked capital baseline</div>
    </div>

    <div class="card">
        <div class="label">Alpaca Sandbox Equity (not your real tracked capital)</div>
        <div class="value">${{ "%.2f"|format(equity) }}</div>
        <div class="risk-note">Your configured tracked capital: ${{ starting_capital }} (see config.py)</div>
    </div>

    <div class="card">
        <div class="label">Strategy Performance: Backtest vs Walk-Forward vs Live Paper Trading</div>
        <table class="sp-table">
            <tr>
                <th>Symbol / Strategy</th>
                <th>Full-Period Backtest</th>
                <th>Walk-Forward (out-of-sample)</th>
                <th>Live Paper Trading</th>
            </tr>
            {% for sp in strategy_performance %}
            <tr>
                <td>
                    <span class="sp-symbol">{{ sp.symbol }}</span><br>
                    <span class="sp-strategy">{{ sp.strategy }}</span>
                </td>
                {% if sp.error %}
                <td colspan="3" class="negative">Could not load: {{ sp.error }}</td>
                {% else %}
                <td>
                    <span class="sp-stage-label">Return</span>{{ sp.backtest.return_pct }}%<br>
                    <span class="sp-stage-label">Sharpe</span>{{ sp.backtest.sharpe }}<br>
                    <span class="sp-stage-label">Win Rate</span>{{ sp.backtest.win_rate_pct }}%
                </td>
                <td>
                    <span class="sp-stage-label">Profitable Windows</span>{{ sp.walk_forward.profitable_windows }}/{{ sp.walk_forward.total_windows }}<br>
                    <span class="sp-stage-label">Avg Sharpe</span>{{ sp.walk_forward.avg_sharpe }}
                </td>
                <td>
                    <span class="sp-stage-label">Realized</span>
                    <span class="{{ 'positive' if sp.live.realized >= 0 else 'negative' }}">{{ "+" if sp.live.realized >= 0 else "" }}${{ "%.2f"|format(sp.live.realized) }}</span><br>
                    <span class="sp-stage-label">Unrealized</span>
                    <span class="{{ 'positive' if sp.live.unrealized >= 0 else 'negative' }}">{{ "+" if sp.live.unrealized >= 0 else "" }}${{ "%.2f"|format(sp.live.unrealized) }}</span><br>
                    <span class="sp-stage-label">Total</span>
                    <span class="{{ 'positive' if sp.live.total >= 0 else 'negative' }}">{{ "+" if sp.live.total >= 0 else "" }}${{ "%.2f"|format(sp.live.total) }}</span>
                </td>
                {% endif %}
            </tr>
            {% endfor %}
        </table>
        <div class="risk-note">Backtest/walk-forward figures cached up to 6 hours (recomputing every page load isn't necessary since they're based on historical data). Live figures are always fresh from Alpaca.</div>
    </div>

    <div class="card">
        <div class="label">Risk Parameters (config.py -&gt; risk/manager.py)</div>
        <div class="risk-grid">
            <div class="risk-item"><div class="rlabel">Max risk per trade</div>
                <div class="rvalue">{{ risk.max_risk_per_trade_pct }}%</div></div>
            <div class="risk-item"><div class="rlabel">Max position size</div>
                <div class="rvalue">{{ risk.max_position_pct }}%</div></div>
            <div class="risk-item"><div class="rlabel">Stop-loss</div>
                <div class="rvalue">{{ risk.stop_loss_pct }}%</div></div>
            <div class="risk-item"><div class="rlabel">Take-profit</div>
                <div class="rvalue">{{ risk.take_profit_pct }}%</div></div>
            <div class="risk-item"><div class="rlabel">Max daily loss (halt)</div>
                <div class="rvalue">{{ risk.max_daily_loss_pct }}%</div></div>
            <div class="risk-item"><div class="rlabel">Max drawdown (halt)</div>
                <div class="rvalue">{{ risk.max_drawdown_pct }}%</div></div>
        </div>
    </div>

    <div class="card">
        <div class="label">Data Sources</div>
        <div class="source-item"><strong>Signals/indicators:</strong> Yahoo Finance (yfinance) - free, ~15-20 min delayed for stocks, near-live for crypto</div>
        <div class="source-item"><strong>Account/positions/execution:</strong> Alpaca paper trading engine - near real-time, simulated fills</div>
        <div class="source-item"><strong>Decision frequency:</strong> once daily (~4:30pm ET, after market close), matching the daily-bar strategies this system was backtested on</div>
    </div>

    <div class="card">
        <div class="label">Open Positions ({{ positions|length }}) - click a row for strategy/indicator detail</div>
        {% if positions %}
            {% for p in positions %}
            <details>
                <summary>
                    <span class="sym">{{ p.symbol }}</span>{% if not p.is_active %}<span class="unmanaged-badge">WATCHLIST - WILL AUTO-CLOSE NEXT CYCLE</span>{% endif %}
                    <span>Qty {{ p.qty }} · ${{ "%.2f"|format(p.market_value) }} ·
                        <span class="{{ 'positive' if p.unrealized_pl >= 0 else 'negative' }}">
                        {{ "+" if p.unrealized_pl >= 0 else "" }}${{ "%.2f"|format(p.unrealized_pl) }}</span>
                    </span>
                </summary>
                <div class="detail-body">
                    <div class="position-grid">
                        <div class="pos-field"><span class="pflabel">Avg Entry</span>
                            <span class="pfvalue">${{ "%.2f"|format(p.avg_entry_price) }}</span></div>
                        <div class="pos-field"><span class="pflabel">Current Price</span>
                            <span class="pfvalue">${{ "%.2f"|format(p.current_price) }}</span></div>
                        <div class="pos-field"><span class="pflabel">Take-Profit</span>
                            <span class="pfvalue tp-value">${{ "%.2f"|format(p.tp_price) }} (+{{ risk.take_profit_pct }}%)</span></div>
                        <div class="pos-field"><span class="pflabel">Stop-Loss</span>
                            <span class="pfvalue sl-value">${{ "%.2f"|format(p.sl_price) }} (-{{ risk.stop_loss_pct }}%)</span></div>
                        <div class="pos-field"><span class="pflabel">Liquidation Price</span>
                            <span class="pfvalue liq-note">N/A - no leverage (cash/spot)</span></div>
                        <div class="pos-field"><span class="pflabel">Market Value</span>
                            <span class="pfvalue">${{ "%.2f"|format(p.market_value) }}</span></div>
                    </div>
                    {% if p.snapshot %}
                    <div class="indicator-row" style="margin-top: 8px;"><span>Strategy</span><span>{{ p.snapshot.strategy }}</span></div>
                    <div class="indicator-row"><span>Current signal</span>
                        <span class="signal-badge {{ 'signal-long' if p.snapshot.signal == 'LONG' else 'signal-flat' }}">{{ p.snapshot.signal }}</span></div>
                    <div class="indicator-row"><span>As of</span><span>{{ p.snapshot.as_of }}</span></div>
                    {% for k, v in p.snapshot.indicators.items() %}
                    <div class="indicator-row"><span>{{ k }}</span><span>{{ v }}</span></div>
                    {% endfor %}
                    {% else %}
                    <div class="indicator-row"><span>Indicator detail unavailable: {{ p.snapshot_error }}</span></div>
                    {% endif %}
                </div>
            </details>
            {% endfor %}
        {% else %}
        <div class="empty">No open positions right now.</div>
        {% endif %}
    </div>

    <div class="card">
        <div class="label">Recent Orders (last 10)</div>
        {% if orders %}
        <table>
            <tr><th>Symbol</th><th>Side</th><th>Qty</th><th>Price</th><th>Status</th><th>Submitted</th></tr>
            {% for o in orders %}
            <tr>
                <td>{{ o.symbol }}</td>
                <td>{{ o.side }}</td>
                <td>{{ o.qty }}</td>
                <td>{{ o.price_display }}</td>
                <td>{{ o.status }}</td>
                <td>{{ o.submitted_at }}</td>
            </tr>
            {% endfor %}
        </table>
        {% else %}
        <div class="empty">No recent orders.</div>
        {% endif %}
    </div>
    {% endif %}
    <div class="risk-note">Auto-refreshes every 5 minutes. Simulated paper trading only - no real money.</div>
</body>
</html>
"""


@app.route("/")
@requires_auth
def dashboard():
    try:
        from alpaca.trading.client import TradingClient

        client = TradingClient(config.ALPACA_API_KEY, config.ALPACA_SECRET_KEY, paper=True)
        account = client.get_account()
        raw_positions = client.get_all_positions()
        from alpaca.trading.requests import GetOrdersRequest as GetOrdersRequestForDisplay
        from alpaca.trading.enums import QueryOrderStatus as QueryOrderStatusForDisplay
        recent_orders_request = GetOrdersRequestForDisplay(
            status=QueryOrderStatusForDisplay.ALL, limit=10,
        )
        raw_orders = client.get_orders(recent_orders_request)
        # Alpaca doesn't guarantee sort order across statuses - sort explicitly, most recent first
        raw_orders = sorted(raw_orders, key=lambda o: o.submitted_at or o.created_at, reverse=True)

        positions = []
        for p in raw_positions:
            lookup_symbol = config.normalize_alpaca_symbol(p.symbol)

            entry = {
                "symbol": p.symbol,
                "qty": p.qty,
                "market_value": float(p.market_value),
                "unrealized_pl": float(p.unrealized_pl),
                "avg_entry_price": float(p.avg_entry_price),
                "current_price": float(p.current_price),
                "tp_price": float(p.avg_entry_price) * (1 + config.TAKE_PROFIT_PCT),
                "sl_price": float(p.avg_entry_price) * (1 - config.STOP_LOSS_PCT),
                "is_active": lookup_symbol in config.SYMBOLS,
                "snapshot": None,
                "snapshot_error": None,
            }
            try:
                entry["snapshot"] = get_indicator_snapshot(lookup_symbol)
            except Exception as snap_err:
                entry["snapshot_error"] = str(snap_err)

            positions.append(entry)

        orders = [{
            "symbol": o.symbol,
            "side": o.side.value if hasattr(o.side, "value") else str(o.side),
            "qty": o.qty,
            "price_display": (f"${float(o.filled_avg_price):.2f} (filled)" if o.filled_avg_price
                               else "Market (pending fill)"),
            "status": o.status.value if hasattr(o.status, "value") else str(o.status),
            "submitted_at": o.submitted_at.strftime("%Y-%m-%d %H:%M") if o.submitted_at else "-",
        } for o in raw_orders[:10]]

        risk = {
            "max_risk_per_trade_pct": round(config.MAX_RISK_PER_TRADE_PCT * 100, 2),
            "max_position_pct": round(config.MAX_POSITION_PCT * 100, 2),
            "stop_loss_pct": round(config.STOP_LOSS_PCT * 100, 2),
            "take_profit_pct": round(config.TAKE_PROFIT_PCT * 100, 2),
            "max_daily_loss_pct": round(config.MAX_DAILY_LOSS_PCT * 100, 2),
            "max_drawdown_pct": round(config.MAX_DRAWDOWN_PCT * 100, 2),
        }

        perf = compute_cumulative_performance(client, positions)

        strategy_performance = []
        for symbol in config.ACTIVE_SYMBOLS:
            entry = {"symbol": symbol, "strategy": config.STRATEGY_MAP.get(symbol, config.STRATEGY),
                      "error": None}
            try:
                bt_wf = compute_backtest_and_walkforward(symbol)
                entry["backtest"] = bt_wf["backtest"]
                entry["walk_forward"] = bt_wf["walk_forward"]
            except Exception as bt_err:
                entry["error"] = str(bt_err)

            live = perf.get("by_symbol", {}).get(symbol, {"realized": 0.0, "unrealized": 0.0, "total": 0.0})
            entry["live"] = live
            strategy_performance.append(entry)

        return render_template_string(
            PAGE_TEMPLATE,
            equity=float(account.equity),
            starting_capital=config.STARTING_CAPITAL,
            positions=positions,
            orders=orders,
            risk=risk,
            perf=perf,
            strategy_performance=strategy_performance,
            error=None,
        )
    except Exception as e:
        return render_template_string(PAGE_TEMPLATE, error=str(e), equity=0,
                                       starting_capital=config.STARTING_CAPITAL,
                                       positions=[], orders=[], risk={}, perf={}, strategy_performance=[])


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
