
import os
import sqlite3
from pathlib import Path
from datetime import datetime, timezone

import pandas as pd
import requests
from dotenv import load_dotenv
from flask import Flask, jsonify, render_template_string

from signal_engine import generate_signal

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

app = Flask(__name__)
API_KEY = os.getenv("TWELVE_DATA_API_KEY", "").strip()
DB_PATH = BASE_DIR / "signals.db"

SYMBOLS = {
    "EUR/USD": "EUR/USD",
    "GBP/USD": "GBP/USD",
    "USD/JPY": "USD/JPY",
    "AUD/USD": "AUD/USD",
    "USD/CAD": "USD/CAD",
}


def init_db():
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS signal_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT,
                signal TEXT,
                entry REAL,
                stop_loss REAL,
                tp1 REAL,
                tp2 REAL,
                tp3 REAL,
                reason TEXT,
                created_at TEXT
            )
        """)


def save_signal(symbol, result):
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("""
            INSERT INTO signal_history
            (symbol, signal, entry, stop_loss, tp1, tp2, tp3,
             reason, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            symbol,
            result.get("signal"),
            result.get("entry"),
            result.get("stop_loss"),
            result.get("tp1"),
            result.get("tp2"),
            result.get("tp3"),
            result.get("reason", ""),
            datetime.now(timezone.utc).isoformat(),
        ))


def get_candles(symbol):
    if not API_KEY:
        raise ValueError(
            "API key missing. Check TWELVE_DATA_API_KEY in .env"
        )

    response = requests.get(
        "https://api.twelvedata.com/time_series",
        params={
            "symbol": symbol,
            "interval": "5min",
            "outputsize": 100,
            "apikey": API_KEY,
        },
        timeout=20,
    )
    response.raise_for_status()
    data = response.json()

    if "values" not in data:
        raise ValueError(
            data.get("message", "Market data unavailable")
        )

    candles = pd.DataFrame(data["values"])
    required = ["open", "high", "low", "close"]

    for column in required:
        if column not in candles.columns:
            raise ValueError(f"Missing candle column: {column}")

        candles[column] = pd.to_numeric(
            candles[column], errors="coerce"
        )

    candles = candles.dropna(subset=required)
    candles = candles.iloc[::-1].reset_index(drop=True)

    if len(candles) < 60:
        raise ValueError(
            f"Only {len(candles)} candles received; 60 required"
        )

    return candles


def build_signal(display_symbol, provider_symbol):
    try:
        candles = get_candles(provider_symbol)
        result = generate_signal(candles)

        result["symbol"] = display_symbol
        result["data_status"] = "connected"

        if result.get("signal") in ("BUY", "SELL"):
            save_signal(display_symbol, result)

        return result

    except Exception as error:
        return {
            "symbol": display_symbol,
            "signal": "WAIT",
            "reason": str(error),
            "entry": None,
            "stop_loss": None,
            "tp1": None,
            "tp2": None,
            "tp3": None,
            "rsi": None,
            "data_status": "error",
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }


HTML_PAGE = """
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>ForexSignals Pro</title>
<style>
body {
    margin: 0;
    padding: 24px;
    font-family: Arial, sans-serif;
    background: #101827;
    color: #f3f4f6;
}
h1 { margin-bottom: 6px; }
.subtitle { color: #9ca3af; margin-bottom: 20px; }
button {
    padding: 10px 16px;
    border: 0;
    border-radius: 7px;
    background: #2563eb;
    color: white;
    cursor: pointer;
}
#status { margin-left: 10px; color: #9ca3af; }
.grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
    gap: 16px;
    margin-top: 20px;
}
.card {
    padding: 18px;
    border-radius: 12px;
    border: 1px solid #374151;
    background: #1f2937;
    overflow-wrap: anywhere;
}
.pair { font-size: 20px; font-weight: bold; }
.signal {
    display: inline-block;
    padding: 7px 12px;
    border-radius: 6px;
    margin: 12px 0;
    font-weight: bold;
}
.BUY { background: #14532d; color: #86efac; }
.SELL { background: #7f1d1d; color: #fecaca; }
.WAIT { background: #374151; color: #e5e7eb; }
.row { margin: 8px 0; }
.reason { color: #9ca3af; font-size: 13px; margin-top: 12px; }
.note { color: #9ca3af; margin-top: 24px; font-size: 13px; }
</style>
</head>
<body>
<h1>ForexSignals Pro</h1>
<div class="subtitle">Forex market signals dashboard</div>
<button onclick="loadSignals()">Refresh Signals</button>
<span id="status">Loading...</span>
<div class="grid" id="signals"></div>
<div class="note">
Signals are educational and not financial advice.
Forex trading involves risk. BUY/SELL signals do not guarantee profit.
</div>

<script>
function addText(parent, className, value) {
    const element = document.createElement("div");
    element.className = className;
    element.textContent = value;
    parent.appendChild(element);
}

function makeCard(item) {
    const card = document.createElement("div");
    card.className = "card";

    addText(card, "pair", item.symbol || "Unknown pair");

    const signal = ["BUY", "SELL", "WAIT"].includes(item.signal)
        ? item.signal : "WAIT";

    addText(card, "signal " + signal, signal);

    const fields = [
        ["Entry", item.entry],
        ["Stop Loss", item.stop_loss],
        ["Take Profit 1", item.tp1],
        ["Take Profit 2", item.tp2],
        ["Take Profit 3", item.tp3],
        ["RSI", item.rsi]
    ];

    fields.forEach(function(field) {
        const value = field[1] == null ? "—" : field[1];
        addText(card, "row", field[0] + ": " + value);
    });

    addText(card, "reason", "Reason: " + (item.reason || "No details"));
    addText(card, "reason", "Data status: " + (item.data_status || "unknown"));

    return card;
}

async function loadSignals() {
    const status = document.getElementById("status");
    const container = document.getElementById("signals");

    status.textContent = "Fetching market data...";
    container.replaceChildren();

    try {
        const response = await fetch("/api/signals");
        const payload = await response.json();

        if (!response.ok || !Array.isArray(payload.signals)) {
            throw new Error(payload.error || "Invalid API response");
        }

        payload.signals.forEach(function(item) {
            container.appendChild(makeCard(item));
        });

        status.textContent = "Updated " + new Date().toLocaleTimeString();
    } catch (error) {
        addText(container, "card", "Error: " + error.message);
        status.textContent = "Failed to load";
    }
}

loadSignals();
setInterval(loadSignals, 60000);
</script>
</body>
</html>
"""


@app.route("/")
def dashboard():
    return render_template_string(HTML_PAGE)


@app.route("/api/signals")
def api_signals():
    results = []

    for display_symbol, provider_symbol in SYMBOLS.items():
        results.append(
            build_signal(display_symbol, provider_symbol)
        )

    return jsonify({
        "signals": results,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    })


@app.route("/api/history")
def api_history():
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute("""
            SELECT symbol, signal, entry, stop_loss, tp1, tp2, tp3,
                   reason, created_at
            FROM signal_history
            ORDER BY id DESC
            LIMIT 100
        """).fetchall()

    return jsonify({
        "history": [dict(row) for row in rows]
    })


@app.route("/health")
def health():
    return jsonify({
        "status": "ok",
        "api_key_loaded": bool(API_KEY),
    })


init_db()

if __name__ == "__main__":
    print("ForexSignals Pro starting...")
    print("API key loaded:", bool(API_KEY))
    app.run(host="127.0.0.1", port=5000, debug=False)
