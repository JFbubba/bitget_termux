import csv
import os
import requests
import time
from datetime import datetime
from pathlib import Path
from account_equity import get_account_equity_usdt
from config import (
    SYMBOLS,
    PRODUCT_TYPE,
    TIMEFRAME,
    CANDLE_LIMIT,
    RISK_PER_TRADE_PERCENT,
    MAX_IMPLIED_LEVERAGE,
    SIGNALS_JOURNAL_FILE,
    OPEN_STATE_FILE as CONFIG_OPEN_STATE_FILE,
    EMA_FAST,
    EMA_SLOW,
    RSI_PERIOD,
    ATR_PERIOD,
    ATR_STOP_MULTIPLIER,
    RISK_REWARD_RATIO,
)


ACCOUNT_EQUITY_USDT, ACCOUNT_EQUITY_SOURCE = get_account_equity_usdt()
JOURNAL_FILE = SIGNALS_JOURNAL_FILE
OPEN_STATE_FILE = Path(CONFIG_OPEN_STATE_FILE)


def load_open_positions():
    if not OPEN_STATE_FILE.exists():
        return set()

    open_positions = set()

    with OPEN_STATE_FILE.open("r", newline="") as csvfile:
        reader = csv.DictReader(csvfile)

        for row in reader:
            symbol = row.get("symbol")
            side = row.get("side")
            outcome = row.get("outcome", "")

            if symbol and side and outcome.startswith("EN COURS"):
                open_positions.add((symbol, side))

    return open_positions


def get_bitget_candles(symbol, product_type=PRODUCT_TYPE, granularity=TIMEFRAME, limit=CANDLE_LIMIT):
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
    candles = get_bitget_candles(symbol=symbol, granularity=TIMEFRAME, limit=CANDLE_LIMIT)
    closes = [candle["close"] for candle in candles]

    ema9_values = ema(closes, EMA_FAST)
    ema21_values = ema(closes, EMA_SLOW)
    rsi_values = calculate_rsi(closes, RSI_PERIOD)
    atr_values = calculate_atr(candles, ATR_PERIOD)

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
        atr_stop = entry - (atr * ATR_STOP_MULTIPLIER)
        stop_loss = min(structural_stop, atr_stop)

        risk_per_unit = entry - stop_loss
        if risk_per_unit <= 0:
            return None

        take_profit = entry + (risk_per_unit * RISK_REWARD_RATIO)
        side = "LONG"

    elif decision in ["SHORT POSSIBLE", "BIAIS SHORT"]:
        structural_stop = recent_high
        atr_stop = entry + (atr * ATR_STOP_MULTIPLIER)
        stop_loss = max(structural_stop, atr_stop)

        risk_per_unit = stop_loss - entry
        if risk_per_unit <= 0:
            return None

        take_profit = entry - (risk_per_unit * RISK_REWARD_RATIO)
        side = "SHORT"

    else:
        return None

    risk_percent_price = (risk_per_unit / entry) * 100
    reward_percent_price = risk_percent_price * 2

    max_risk_usdt = ACCOUNT_EQUITY_USDT * (RISK_PER_TRADE_PERCENT / 100)
    base_size = max_risk_usdt / risk_per_unit
    notional_position_usdt = base_size * entry
    implied_leverage = notional_position_usdt / ACCOUNT_EQUITY_USDT

    accepted = implied_leverage <= MAX_IMPLIED_LEVERAGE

    if accepted:
        status = "ACCEPTÉ"
        rejection_reason = ""
    else:
        status = "REFUSÉ"
        rejection_reason = (
            f"levier implicite {implied_leverage:.2f}x > "
            f"max {MAX_IMPLIED_LEVERAGE:.2f}x"
        )

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
        "accepted": accepted,
        "status": status,
        "rejection_reason": rejection_reason,
    }


def rank_score(analysis, plan):
    if plan is None:
        return -999

    score = analysis["score"]

    if plan["accepted"]:
        score += 2
    else:
        score -= 2

    if 55 <= analysis["rsi"] <= 65:
        score += 1

    if analysis["atr_percent"] > 1.0:
        score -= 1

    return score


def append_to_journal(rows):
    if not rows:
        return

    file_exists = os.path.exists(JOURNAL_FILE)

    fieldnames = [
        "timestamp",
        "symbol",
        "price",
        "decision",
        "score",
        "ranking",
        "rsi",
        "atr_percent",
        "ema_distance_percent",
        "status",
        "side",
        "entry",
        "stop_loss",
        "take_profit",
        "risk_percent_price",
        "notional_position_usdt",
        "implied_leverage",
        "rejection_reason",
        "reasons",
    ]

    with open(JOURNAL_FILE, "a", newline="") as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)

        if not file_exists:
            writer.writeheader()

        for row in rows:
            writer.writerow(row)


def build_journal_row(analysis, plan, ranking):
    now = datetime.now().isoformat(timespec="seconds")

    base = {
        "timestamp": now,
        "symbol": analysis["symbol"],
        "price": analysis["last_close"],
        "decision": analysis["decision"],
        "score": analysis["score"],
        "ranking": ranking,
        "rsi": round(analysis["rsi"], 4),
        "atr_percent": round(analysis["atr_percent"], 4),
        "ema_distance_percent": round(analysis["ema_distance_percent"], 4),
        "reasons": "|".join(analysis["reasons"]),
    }

    if plan is None:
        base.update({
            "status": "PAS DE PLAN",
            "side": "",
            "entry": "",
            "stop_loss": "",
            "take_profit": "",
            "risk_percent_price": "",
            "notional_position_usdt": "",
            "implied_leverage": "",
            "rejection_reason": "",
        })
    else:
        base.update({
            "status": plan["status"],
            "side": plan["side"],
            "entry": round(plan["entry"], 8),
            "stop_loss": round(plan["stop_loss"], 8),
            "take_profit": round(plan["take_profit"], 8),
            "risk_percent_price": round(plan["risk_percent_price"], 4),
            "notional_position_usdt": round(plan["notional_position_usdt"], 4),
            "implied_leverage": round(plan["implied_leverage"], 4),
            "rejection_reason": plan["rejection_reason"],
        })

    return base


def format_line(analysis, plan, ranking):
    if plan is None:
        return (
            f"{analysis['symbol']:<10} "
            f"PAS DE PLAN | "
            f"Prix: {analysis['last_close']:>12,.4f} | "
            f"Score: {analysis['score']:>2} | "
            f"RSI: {analysis['rsi']:>6.2f} | "
            f"ATR%: {analysis['atr_percent']:>6.3f}% | "
            f"Décision: {analysis['decision']:<14}"
        )

    line = (
        f"{analysis['symbol']:<10} "
        f"{plan['status']:<7} | "
        f"{plan['side']:<5} | "
        f"Rank: {ranking:>2} | "
        f"Prix: {analysis['last_close']:>12,.4f} | "
        f"Score: {analysis['score']:>2} | "
        f"RSI: {analysis['rsi']:>6.2f} | "
        f"SL: {plan['stop_loss']:>12,.4f} | "
        f"TP: {plan['take_profit']:>12,.4f} | "
        f"Lev: {plan['implied_leverage']:>5.2f}x"
    )

    if not plan["accepted"]:
        line += f" | {plan['rejection_reason']}"

    return line


if __name__ == "__main__":
    print("=== BITGET JOURNAL SCANNER ===")
    print(f"Journal: {JOURNAL_FILE}")
    print("Statut: ANALYSE SEULEMENT — aucun ordre envoyé.")
    print(f"Equity utilisée: {ACCOUNT_EQUITY_USDT} USDT | Source: {ACCOUNT_EQUITY_SOURCE}")
    print()

    open_positions = load_open_positions()

    if open_positions:
        readable_positions = [f"{symbol} {side}" for symbol, side in sorted(open_positions)]
        print(f"Positions déjà ouvertes ignorées dans le même sens: {', '.join(readable_positions)}")
        print()

    results = []
    journal_rows = []

    for symbol in SYMBOLS:
        try:
            analysis = analyze_symbol(symbol)
            plan = build_trade_plan(analysis)

            if plan is not None and (symbol, plan["side"]) in open_positions:
                print(f"{symbol:<10} IGNORÉ | {plan['side']} déjà ouvert")
                continue

            ranking = rank_score(analysis, plan)

            results.append({
                "analysis": analysis,
                "plan": plan,
                "ranking": ranking,
            })

            time.sleep(0.2)

        except Exception as error:
            print(f"{symbol:<10} ERREUR: {error}")

    results.sort(key=lambda item: item["ranking"], reverse=True)

    for item in results:
        analysis = item["analysis"]
        plan = item["plan"]
        ranking = item["ranking"]

        print(format_line(analysis, plan, ranking))
        journal_rows.append(build_journal_row(analysis, plan, ranking))

    append_to_journal(journal_rows)

    print()
    print(f"{len(journal_rows)} lignes ajoutées au journal: {JOURNAL_FILE}")