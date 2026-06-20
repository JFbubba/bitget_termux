import requests
import time
from datetime import datetime


SYMBOLS = [
    "BTCUSDT",
    "ETHUSDT",
    "SOLUSDT",
    "XRPUSDT",
    "XAUTUSDT",
]

ACCOUNT_EQUITY_USDT = 100.0
RISK_PER_TRADE_PERCENT = 1.0


def get_bitget_candles(symbol, product_type="USDT-FUTURES", granularity="15m", limit=100):
    url = "https://api.bitget.com/api/v2/mix/market/candles"

    params = {
        "symbol": symbol,
        "productType": product_type,
        "granularity": granularity,
        "limit": str(limit),
    }

    response = requests.get(url, params=params, timeout=10)
    response.raise_for_status()

    result = response.json()

    if result.get("code") != "00000":
        raise RuntimeError(f"Erreur Bitget pour {symbol}: {result}")

    candles = []

    for row in result["data"]:
        timestamp_ms = int(row[0])
        candles.append({
            "time": datetime.fromtimestamp(timestamp_ms / 1000),
            "open": float(row[1]),
            "high": float(row[2]),
            "low": float(row[3]),
            "close": float(row[4]),
            "volume_base": float(row[5]),
            "volume_quote": float(row[6]),
        })

    candles.sort(key=lambda x: x["time"])
    return candles


def ema(values, period):
    multiplier = 2 / (period + 1)
    ema_values = [sum(values[:period]) / period]

    for price in values[period:]:
        ema_values.append((price - ema_values[-1]) * multiplier + ema_values[-1])

    return ema_values


def calculate_rsi(values, period=14):
    gains = []
    losses = []

    for i in range(1, period + 1):
        change = values[i] - values[i - 1]
        gains.append(max(change, 0))
        losses.append(abs(min(change, 0)))

    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period

    rsi_values = []

    if avg_loss == 0:
        rsi_values.append(100)
    else:
        rs = avg_gain / avg_loss
        rsi_values.append(100 - (100 / (1 + rs)))

    for i in range(period + 1, len(values)):
        change = values[i] - values[i - 1]
        gain = max(change, 0)
        loss = abs(min(change, 0))

        avg_gain = ((avg_gain * (period - 1)) + gain) / period
        avg_loss = ((avg_loss * (period - 1)) + loss) / period

        if avg_loss == 0:
            rsi_values.append(100)
        else:
            rs = avg_gain / avg_loss
            rsi_values.append(100 - (100 / (1 + rs)))

    return rsi_values


def calculate_atr(candles, period=14):
    true_ranges = []

    for i in range(1, len(candles)):
        high = candles[i]["high"]
        low = candles[i]["low"]
        previous_close = candles[i - 1]["close"]

        tr = max(
            high - low,
            abs(high - previous_close),
            abs(low - previous_close),
        )

        true_ranges.append(tr)

    atr_values = [sum(true_ranges[:period]) / period]

    for tr in true_ranges[period:]:
        atr_values.append(((atr_values[-1] * (period - 1)) + tr) / period)

    return atr_values


def analyze_symbol(symbol):
    candles = get_bitget_candles(symbol=symbol, granularity="15m", limit=100)
    closes = [candle["close"] for candle in candles]

    ema9_values = ema(closes, 9)
    ema21_values = ema(closes, 21)
    rsi_values = calculate_rsi(closes, 14)
    atr_values = calculate_atr(candles, 14)

    last_close = closes[-1]
    last_ema9 = ema9_values[-1]
    last_ema21 = ema21_values[-1]
    last_rsi = rsi_values[-1]
    last_atr = atr_values[-1]

    ema_distance_percent = ((last_ema9 - last_ema21) / last_ema21) * 100
    atr_percent = (last_atr / last_close) * 100

    score = 0
    reasons = []

    if last_ema9 > last_ema21:
        score += 1
        reasons.append("EMA+")
    elif last_ema9 < last_ema21:
        score -= 1
        reasons.append("EMA-")

    if ema_distance_percent > 0.05:
        score += 1
        reasons.append("EMA distance+")
    elif ema_distance_percent < -0.05:
        score -= 1
        reasons.append("EMA distance-")

    if 55 <= last_rsi < 70:
        score += 1
        reasons.append("RSI+")
    elif 30 < last_rsi <= 45:
        score -= 1
        reasons.append("RSI-")
    elif last_rsi >= 70:
        score -= 1
        reasons.append("RSI surachat")
    elif last_rsi <= 30:
        score += 1
        reasons.append("RSI survente")

    if score >= 3:
        decision = "LONG POSSIBLE"
    elif score <= -3:
        decision = "SHORT POSSIBLE"
    elif score == 2:
        decision = "BIAIS LONG"
    elif score == -2:
        decision = "BIAIS SHORT"
    else:
        decision = "NEUTRE"

    return {
        "symbol": symbol,
        "last_close": last_close,
        "ema_distance_percent": ema_distance_percent,
        "rsi": last_rsi,
        "atr": last_atr,
        "atr_percent": atr_percent,
        "score": score,
        "decision": decision,
        "reasons": reasons,
        "candles": candles,
    }


def build_trade_plan(analysis):
    decision = analysis["decision"]
    entry = analysis["last_close"]
    candles = analysis["candles"]
    atr = analysis["atr"]

    recent_lows = [candle["low"] for candle in candles[-10:]]
    recent_highs = [candle["high"] for candle in candles[-10:]]

    recent_low = min(recent_lows)
    recent_high = max(recent_highs)

    if decision in ["LONG POSSIBLE", "BIAIS LONG"]:
        structural_stop = recent_low
        atr_stop = entry - (atr * 1.5)
        stop_loss = min(structural_stop, atr_stop)

        risk_per_unit = entry - stop_loss
        if risk_per_unit <= 0:
            return None

        take_profit = entry + (risk_per_unit * 2)
        side = "LONG"

    elif decision in ["SHORT POSSIBLE", "BIAIS SHORT"]:
        structural_stop = recent_high
        atr_stop = entry + (atr * 1.5)
        stop_loss = max(structural_stop, atr_stop)

        risk_per_unit = stop_loss - entry
        if risk_per_unit <= 0:
            return None

        take_profit = entry - (risk_per_unit * 2)
        side = "SHORT"

    else:
        return None

    risk_percent_price = (risk_per_unit / entry) * 100
    reward_percent_price = risk_percent_price * 2

    max_risk_usdt = ACCOUNT_EQUITY_USDT * (RISK_PER_TRADE_PERCENT / 100)
    base_size = max_risk_usdt / risk_per_unit
    notional_position_usdt = base_size * entry
    implied_leverage = notional_position_usdt / ACCOUNT_EQUITY_USDT

    return {
        "side": side,
        "entry": entry,
        "stop_loss": stop_loss,
        "take_profit": take_profit,
        "risk_percent_price": risk_percent_price,
        "reward_percent_price": reward_percent_price,
        "base_size": base_size,
        "notional_position_usdt": notional_position_usdt,
        "implied_leverage": implied_leverage,
    }


def print_result(analysis, plan):
    reasons = ",".join(analysis["reasons"])

    if plan is None:
        print(
            f"{analysis['symbol']:<10} "
            f"Prix: {analysis['last_close']:>12,.4f} | "
            f"Score: {analysis['score']:>2} | "
            f"RSI: {analysis['rsi']:>6.2f} | "
            f"ATR%: {analysis['atr_percent']:>6.3f}% | "
            f"Décision: {analysis['decision']:<14} | "
            f"{reasons}"
        )
    else:
        print(
            f"{analysis['symbol']:<10} "
            f"{plan['side']:<5} | "
            f"Prix: {analysis['last_close']:>12,.4f} | "
            f"Score: {analysis['score']:>2} | "
            f"RSI: {analysis['rsi']:>6.2f} | "
            f"SL: {plan['stop_loss']:>12,.4f} | "
            f"TP: {plan['take_profit']:>12,.4f} | "
            f"Risque: {plan['risk_percent_price']:>6.3f}% | "
            f"Notionnel: {plan['notional_position_usdt']:>8.2f} USDT | "
            f"Lev: {plan['implied_leverage']:>5.2f}x"
        )


if __name__ == "__main__":
    print("=== BITGET PORTFOLIO SCANNER ===")
    print(f"Capital théorique: {ACCOUNT_EQUITY_USDT:.2f} USDT")
    print(f"Risque par trade: {RISK_PER_TRADE_PERCENT:.2f}%")
    print("Statut: ANALYSE SEULEMENT — aucun ordre envoyé.")
    print()

    for symbol in SYMBOLS:
        try:
            analysis = analyze_symbol(symbol)
            plan = build_trade_plan(analysis)
            print_result(analysis, plan)
            time.sleep(0.2)
        except Exception as error:
            print(f"{symbol:<10} ERREUR: {error}")
