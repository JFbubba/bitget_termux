"""
indicators.py — fonctions d'indicateurs pures et testables.

Classement : SAFE (calcul pur, aucune I/O, aucun ordre).

But du patch :
  - Centraliser EMA / RSI / ATR pour qu'ils soient testables unitairement.
  - Corriger le BUG SILENCIEUX : si l'API renvoie moins de bougies que la
    période demandée, l'ancienne EMA divisait par `period` (et non par le
    nombre réel de valeurs) et renvoyait une valeur fausse SANS erreur.
    Ici on lève une ValueError explicite -> le symbole est ignoré proprement
    au lieu de produire un signal basé sur des indicateurs faux.

Intégration dans journal_scanner.py :
    from indicators import ema, calculate_rsi, calculate_atr
  (et supprimer les définitions locales correspondantes).
"""


def _require(values, period, name):
    if period <= 0:
        raise ValueError(f"{name}: période invalide ({period})")
    if len(values) < period + 1:
        raise ValueError(
            f"{name}: données insuffisantes "
            f"({len(values)} valeurs pour une période de {period})"
        )


def ema(values, period):
    """EMA Wilder/SMA-seed. Lève ValueError si données insuffisantes."""
    _require(values, period, "EMA")
    multiplier = 2 / (period + 1)
    ema_values = [sum(values[:period]) / period]
    for price in values[period:]:
        ema_values.append((price - ema_values[-1]) * multiplier + ema_values[-1])
    return ema_values


def calculate_rsi(values, period=14):
    """RSI Wilder. Lève ValueError si données insuffisantes."""
    _require(values, period, "RSI")
    gains, losses = [], []
    for i in range(1, period + 1):
        change = values[i] - values[i - 1]
        gains.append(max(change, 0))
        losses.append(abs(min(change, 0)))

    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period

    rsi_values = []
    rsi_values.append(100.0 if avg_loss == 0 else 100 - (100 / (1 + avg_gain / avg_loss)))

    for i in range(period + 1, len(values)):
        change = values[i] - values[i - 1]
        gain = max(change, 0)
        loss = abs(min(change, 0))
        avg_gain = ((avg_gain * (period - 1)) + gain) / period
        avg_loss = ((avg_loss * (period - 1)) + loss) / period
        rsi_values.append(100.0 if avg_loss == 0 else 100 - (100 / (1 + avg_gain / avg_loss)))

    return rsi_values


def calculate_atr(candles, period=14):
    """ATR Wilder à partir de bougies {high, low, close}. Lève ValueError si insuffisant."""
    if len(candles) < period + 1:
        raise ValueError(
            f"ATR: données insuffisantes ({len(candles)} bougies pour une période de {period})"
        )
    true_ranges = []
    for i in range(1, len(candles)):
        high = candles[i]["high"]
        low = candles[i]["low"]
        previous_close = candles[i - 1]["close"]
        tr = max(high - low, abs(high - previous_close), abs(low - previous_close))
        true_ranges.append(tr)

    atr_values = [sum(true_ranges[:period]) / period]
    for tr in true_ranges[period:]:
        atr_values.append(((atr_values[-1] * (period - 1)) + tr) / period)
    return atr_values
