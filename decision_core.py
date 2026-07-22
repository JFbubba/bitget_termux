"""
decision_core.py — cœur PUR partagé des CLIs d'analyse de première génération
(decision_engine / trade_plan / position_sizer / atr_trade_plan).

Classement : SAFE (calcul pur, aucune I/O, aucun ordre). Extrait À L'IDENTIQUE de
quatre quasi-clones — refactor sans changement de comportement : chaque wrapper
garde son interface et la FORME exacte de ses dicts d'origine (clés comprises).
Aucun consommateur runtime : ces modules sont des CLIs d'analyse manuelle ;
le cerveau réel passe par swarm_brain/journal_scanner.

Les drapeaux d'analyse/plan encodent les variations historiques entre clones :
  • with_atr        : position_sizer/atr_trade_plan calculent l'ATR, pas les autres ;
  • with_ema_levels : decision_engine/trade_plan exposent ema9/ema21 bruts ;
  • include_candles : decision_engine ne renvoie PAS les bougies ;
  • use_atr_stop    : stop = le plus LARGE de (structurel, ATR×1.5) vs structurel seul ;
  • include_risk_per_unit : position_sizer expose le risque par unité (sizing).
"""

from indicators import ema, calculate_rsi, calculate_atr


def score_signaux(last_ema9, last_ema21, ema_distance_percent, last_rsi):
    """Score EMA/RSI commun aux quatre clones. Pur."""
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

    return score, reasons


def decision_label(score):
    """Étiquette de décision commune. Pur."""
    if score >= 3:
        return "LONG POSSIBLE"
    if score <= -3:
        return "SHORT POSSIBLE"
    if score == 2:
        return "BIAIS LONG"
    if score == -2:
        return "BIAIS SHORT"
    return "NEUTRE / ATTENDRE"


def analyze(symbol, candles, with_atr=False, with_ema_levels=False,
            include_candles=True):
    """Analyse EMA9/EMA21 + RSI (+ ATR) sur bougies INJECTÉES. Pur."""
    closes = [candle["close"] for candle in candles]

    ema9_values = ema(closes, 9)
    ema21_values = ema(closes, 21)
    rsi_values = calculate_rsi(closes, 14)

    last_close = closes[-1]
    last_ema9 = ema9_values[-1]
    last_ema21 = ema21_values[-1]
    last_rsi = rsi_values[-1]

    ema_distance_percent = ((last_ema9 - last_ema21) / last_ema21) * 100

    out = {"symbol": symbol, "last_close": last_close}
    if with_ema_levels:
        out["ema9"] = last_ema9
        out["ema21"] = last_ema21
    out["ema_distance_percent"] = ema_distance_percent
    out["rsi"] = last_rsi
    if with_atr:
        last_atr = calculate_atr(candles, 14)[-1]
        out["atr"] = last_atr
        out["atr_percent"] = (last_atr / last_close) * 100

    score, reasons = score_signaux(last_ema9, last_ema21,
                                   ema_distance_percent, last_rsi)
    out["score"] = score
    out["decision"] = decision_label(score)
    out["reasons"] = reasons
    if include_candles:
        out["candles"] = candles
    return out


def build_plan(analysis, rr, use_atr_stop, include_risk_per_unit=False):
    """Plan LONG/SHORT depuis une analyse INJECTÉE. Pur. None si signal
    insuffisant ou risque nul — jamais de plan à risque inversé."""
    decision = analysis["decision"]
    entry = analysis["last_close"]
    candles = analysis["candles"]

    recent_low = min(candle["low"] for candle in candles[-10:])
    recent_high = max(candle["high"] for candle in candles[-10:])

    if decision in ("LONG POSSIBLE", "BIAIS LONG"):
        structural_stop = recent_low
        if use_atr_stop:
            atr_stop = entry - (analysis["atr"] * 1.5)
            stop_loss = min(structural_stop, atr_stop)
        else:
            stop_loss = structural_stop

        risk = entry - stop_loss
        if risk <= 0:
            return None
        take_profit = entry + (risk * rr)

        plan = {"side": "LONG", "entry": entry, "stop_loss": stop_loss}
        if use_atr_stop:
            plan["structural_stop"] = structural_stop
            plan["atr_stop"] = atr_stop
        plan["take_profit"] = take_profit
        if include_risk_per_unit:
            plan["risk_per_unit"] = risk
        plan["risk_percent"] = (risk / entry) * 100
        plan["reward_percent"] = ((take_profit - entry) / entry) * 100
        plan["reward_risk_ratio"] = (take_profit - entry) / risk
        return plan

    if decision in ("SHORT POSSIBLE", "BIAIS SHORT"):
        structural_stop = recent_high
        if use_atr_stop:
            atr_stop = entry + (analysis["atr"] * 1.5)
            stop_loss = max(structural_stop, atr_stop)
        else:
            stop_loss = structural_stop

        risk = stop_loss - entry
        if risk <= 0:
            return None
        take_profit = entry - (risk * rr)

        plan = {"side": "SHORT", "entry": entry, "stop_loss": stop_loss}
        if use_atr_stop:
            plan["structural_stop"] = structural_stop
            plan["atr_stop"] = atr_stop
        plan["take_profit"] = take_profit
        if include_risk_per_unit:
            plan["risk_per_unit"] = risk
        plan["risk_percent"] = (risk / entry) * 100
        plan["reward_percent"] = ((entry - take_profit) / entry) * 100
        plan["reward_risk_ratio"] = (entry - take_profit) / risk
        return plan

    return None
