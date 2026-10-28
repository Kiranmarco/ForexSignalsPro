
from datetime import datetime, timezone

import pandas as pd


def generate_signal(candles):
    """
    Rule-based demo strategy.

    candles must contain:
    open, high, low, close
    Use completed candles from a real market-data source.
    """

    required = {"open", "high", "low", "close"}

    if candles is None or not required.issubset(candles.columns):
        return {"signal": "WAIT", "reason": "Missing candle data"}

    if len(candles) < 60:
        return {"signal": "WAIT", "reason": "Need at least 60 candles"}

    df = candles.copy()

    for column in required:
        df[column] = pd.to_numeric(df[column], errors="coerce")

    df = df.dropna(subset=list(required))

    if len(df) < 60:
        return {"signal": "WAIT", "reason": "Insufficient valid candles"}

    # Moving averages
    df["ema20"] = df["close"].ewm(span=20, adjust=False).mean()
    df["ema50"] = df["close"].ewm(span=50, adjust=False).mean()

    # RSI (14-period)
    change = df["close"].diff()
    gain = change.clip(lower=0)
    loss = -change.clip(upper=0)

    avg_gain = gain.ewm(
        alpha=1 / 14, min_periods=14, adjust=False
    ).mean()
    avg_loss = loss.ewm(
        alpha=1 / 14, min_periods=14, adjust=False
    ).mean()

    relative_strength = avg_gain / avg_loss
    df["rsi"] = 100 - (100 / (1 + relative_strength))

    latest = df.iloc[-1]
    previous = df.iloc[-2]

    entry = float(latest["close"])
    ema20 = float(latest["ema20"])
    ema50 = float(latest["ema50"])
    rsi = float(latest["rsi"])

    # Use recent completed candles to estimate volatility.
    recent = df.iloc[-15:-1]
    candle_range = recent["high"] - recent["low"]
    volatility = float(candle_range.median())

    if (
        not all(pd.notna(x) for x in [entry, ema20, ema50, rsi, volatility])
        or entry <= 0
        or volatility <= 0
    ):
        return {"signal": "WAIT", "reason": "Invalid price or volatility data"}

    # Trend + momentum rules.
    buy = (
        ema20 > ema50
        and entry > ema20
        and 50 < rsi < 68
        and latest["close"] > previous["high"]
    )

    sell = (
        ema20 < ema50
        and entry < ema20
        and 32 < rsi < 50
        and latest["close"] < previous["low"]
    )

    if not buy and not sell:
        return {
            "signal": "WAIT",
            "reason": "Trend and momentum conditions do not align",
            "entry": round(entry, 5),
            "rsi": round(rsi, 2),
            "strategy": "EMA 20/50 + RSI 14 + candle breakout",
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }

    # Volatility-based stop and reward targets.
    direction = 1 if buy else -1
    stop_distance = 1.5 * volatility
    risk = stop_distance

    stop_loss = entry - direction * stop_distance
    tp1 = entry + direction * risk
    tp2 = entry + direction * risk * 2
    tp3 = entry + direction * risk * 3

    return {
        "signal": "BUY" if buy else "SELL",
        "reason": "Trend, momentum and breakout conditions aligned",
        "strategy": "EMA 20/50 + RSI 14 + candle breakout",
        "entry": round(entry, 5),
        "stop_loss": round(stop_loss, 5),
        "tp1": round(tp1, 5),
        "tp2": round(tp2, 5),
        "tp3": round(tp3, 5),
        "rsi": round(rsi, 2),
        "risk_distance": round(risk, 5),
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
