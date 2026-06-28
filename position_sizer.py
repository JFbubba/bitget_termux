

ACCOUNT_EQUITY_USDT = 100.0
RISK_PER_TRADE_PERCENT = 1.0


from candle_reader import get_bitget_candles


from indicators import ema, calculate_rsi, calculate_atr


def analyze_decision(symbol="BTCUSDT"):
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
        reasons.append("EMA9 > EMA21")
    elif last_ema9 < last_ema21:
        score -= 1
        reasons.append("EMA9 < EMA21")

    if ema_distance_percent > 0.05:
        score += 1
        reasons.append("distance EMA haussière significative")
    elif ema_distance_percent < -0.05:
        score -= 1
        reasons.append("distance EMA baissière significative")

    if 55 <= last_rsi < 70:
        score += 1
        reasons.append("RSI haussier sans surachat")
    elif 30 < last_rsi <= 45:
        score -= 1
        reasons.append("RSI baissier sans survente")
    elif last_rsi >= 70:
        score -= 1
        reasons.append("RSI en surachat")
    elif last_rsi <= 30:
        score += 1
        reasons.append("RSI en survente")

    if score >= 3:
        decision = "LONG POSSIBLE"
    elif score <= -3:
        decision = "SHORT POSSIBLE"
    elif score == 2:
        decision = "BIAIS LONG"
    elif score == -2:
        decision = "BIAIS SHORT"
    else:
        decision = "NEUTRE / ATTENDRE"

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

        return {
            "side": "LONG",
            "entry": entry,
            "stop_loss": stop_loss,
            "structural_stop": structural_stop,
            "atr_stop": atr_stop,
            "take_profit": take_profit,
            "risk_per_unit": risk_per_unit,
            "risk_percent": (risk_per_unit / entry) * 100,
            "reward_percent": ((take_profit - entry) / entry) * 100,
            "reward_risk_ratio": (take_profit - entry) / risk_per_unit,
        }

    if decision in ["SHORT POSSIBLE", "BIAIS SHORT"]:
        structural_stop = recent_high
        atr_stop = entry + (atr * 1.5)
        stop_loss = max(structural_stop, atr_stop)

        risk_per_unit = stop_loss - entry
        if risk_per_unit <= 0:
            return None

        take_profit = entry - (risk_per_unit * 2)

        return {
            "side": "SHORT",
            "entry": entry,
            "stop_loss": stop_loss,
            "structural_stop": structural_stop,
            "atr_stop": atr_stop,
            "take_profit": take_profit,
            "risk_per_unit": risk_per_unit,
            "risk_percent": (risk_per_unit / entry) * 100,
            "reward_percent": ((entry - take_profit) / entry) * 100,
            "reward_risk_ratio": (entry - take_profit) / risk_per_unit,
        }

    return None


def calculate_position_size(plan, account_equity, risk_percent):
    max_risk_usdt = account_equity * (risk_percent / 100)
    risk_per_btc = plan["risk_per_unit"]

    btc_size = max_risk_usdt / risk_per_btc
    notional_position_usdt = btc_size * plan["entry"]

    return {
        "account_equity": account_equity,
        "risk_percent": risk_percent,
        "max_risk_usdt": max_risk_usdt,
        "btc_size": btc_size,
        "notional_position_usdt": notional_position_usdt,
    }


if __name__ == "__main__":
    analysis = analyze_decision("BTCUSDT")
    plan = build_trade_plan(analysis)

    print("=== BITGET POSITION SIZER ===")
    print(f"Symbole: {analysis['symbol']}")
    print(f"Décision: {analysis['decision']}")
    print(f"Score: {analysis['score']}")
    print(f"RSI 14: {analysis['rsi']:.2f}")
    print(f"Distance EMA9/EMA21: {analysis['ema_distance_percent']:.4f}%")
    print(f"ATR 14: {analysis['atr']:.2f}")
    print(f"ATR %: {analysis['atr_percent']:.4f}%")
    print()

    if plan is None:
        print("Aucun plan exploitable : signal insuffisant ou risque invalide.")
    else:
        sizing = calculate_position_size(
            plan,
            ACCOUNT_EQUITY_USDT,
            RISK_PER_TRADE_PERCENT
        )

        print("Plan théorique:")
        print(f"Side: {plan['side']}")
        print(f"Entrée: {plan['entry']:.2f}")
        print(f"Stop-loss: {plan['stop_loss']:.2f}")
        print(f"Take-profit: {plan['take_profit']:.2f}")
        print(f"Risque prix par BTC: {plan['risk_per_unit']:.2f} USDT")
        print(f"Risque % prix: {plan['risk_percent']:.3f}%")
        print(f"Gain potentiel: {plan['reward_percent']:.3f}%")
        print(f"Ratio reward/risk: {plan['reward_risk_ratio']:.2f}")
        print()

        print("Money management:")
        print(f"Capital théorique: {sizing['account_equity']:.2f} USDT")
        print(f"Risque par trade: {sizing['risk_percent']:.2f}%")
        print(f"Risque maximum: {sizing['max_risk_usdt']:.2f} USDT")
        print(f"Taille position: {sizing['btc_size']:.8f} BTC")
        print(f"Valeur notionnelle: {sizing['notional_position_usdt']:.2f} USDT")
        print()
        print("Statut: ANALYSE SEULEMENT — aucun ordre envoyé.")
