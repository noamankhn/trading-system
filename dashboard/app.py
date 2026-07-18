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
    </style>
</head>
<body>
    <h1>Paper Trading Dashboard</h1>
    {% if error %}
        <div class="error">Could not load Alpaca data: {{ error }}</div>
    {% else %}
    <div class="card">
        <div class="label">Alpaca Sandbox Equity (not your real tracked capital)</div>
        <div class="value">${{ "%.2f"|format(equity) }}</div>
        <div class="risk-note">Your configured tracked capital: ${{ starting_capital }} (see config.py)</div>
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
                    <span class="sym">{{ p.symbol }}</span>
                    <span>Qty {{ p.qty }} · ${{ "%.2f"|format(p.market_value) }} ·
                        <span class="{{ 'positive' if p.unrealized_pl >= 0 else 'negative' }}">
                        {{ "+" if p.unrealized_pl >= 0 else "" }}${{ "%.2f"|format(p.unrealized_pl) }}</span>
                    </span>
                </summary>
                <div class="detail-body">
                    {% if p.snapshot %}
                    <div class="indicator-row"><span>Strategy</span><span>{{ p.snapshot.strategy }}</span></div>
                    <div class="indicator-row"><span>Current signal</span>
                        <span class="signal-badge {{ 'signal-long' if p.snapshot.signal == 'LONG' else 'signal-flat' }}">{{ p.snapshot.signal }}</span></div>
                    <div class="indicator-row"><span>Last close</span><span>${{ p.snapshot.close }}</span></div>
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
            <tr><th>Symbol</th><th>Side</th><th>Qty</th><th>Status</th><th>Submitted</th></tr>
            {% for o in orders %}
            <tr>
                <td>{{ o.symbol }}</td>
                <td>{{ o.side }}</td>
                <td>{{ o.qty }}</td>
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
        raw_orders = client.get_orders()

        positions = []
        for p in raw_positions:
            # Alpaca crypto positions use "BTCUSD" style symbols; our config/data layer
            # uses "BTC-USD" - normalize so we can look up the right strategy/indicators.
            lookup_symbol = p.symbol
            if lookup_symbol.endswith("USD") and "-" not in lookup_symbol and "/" not in lookup_symbol:
                base = lookup_symbol[:-3]
                candidate = f"{base}-USD"
                if candidate in config.ALL_KNOWN_SYMBOLS:
                    lookup_symbol = candidate

            entry = {
                "symbol": p.symbol,
                "qty": p.qty,
                "market_value": float(p.market_value),
                "unrealized_pl": float(p.unrealized_pl),
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

        return render_template_string(
            PAGE_TEMPLATE,
            equity=float(account.equity),
            starting_capital=config.STARTING_CAPITAL,
            positions=positions,
            orders=orders,
            risk=risk,
            error=None,
        )
    except Exception as e:
        return render_template_string(PAGE_TEMPLATE, error=str(e), equity=0,
                                       starting_capital=config.STARTING_CAPITAL,
                                       positions=[], orders=[], risk={})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
