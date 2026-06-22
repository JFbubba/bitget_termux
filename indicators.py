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


def volume_anchored_level(candles, lookback=20):
    """Niveau S/R ancré au volume : clôture de la bougie au plus gros volume
    sur les `lookback` dernières bougies.

    Concept réimplémenté indépendamment d'après "Unbiased Level Pro"
    (cf. docs/EXTERNAL_TOOLS.md). Bougies : {"close", "volume", ...}.
    SAFE : calcul pur, aucune I/O, aucun ordre.
    """
    if lookback <= 0:
        raise ValueError(f"volume_anchored_level: lookback invalide ({lookback})")
    if not candles:
        raise ValueError("volume_anchored_level: aucune bougie fournie")
    window = candles[-lookback:]
    top = max(window, key=lambda c: float(c.get("volume", 0.0)))
    return float(top["close"])


def volume_bias_score(candles, lookback=20):
    """Score de biais directionnel pondéré par le volume sur `lookback` bougies.

    Pour chaque bougie : sens (close vs open) et volume en hausse vs la
    précédente. Conviction :
      haussière + volume en hausse -> +3 ; haussière + volume en baisse -> +1
      baissière + volume en hausse -> -3 ; baissière + volume en baisse -> -1
      close == open (doji) -> 0
    Score net > 0 = biais acheteur, < 0 = biais vendeur.

    Concept réimplémenté d'après "Unbiased Level Pro". SAFE : calcul pur.
    """
    if lookback <= 0:
        raise ValueError(f"volume_bias_score: lookback invalide ({lookback})")
    window = candles[-lookback:]
    score = 0
    prev_volume = None
    for candle in window:
        volume = float(candle.get("volume", 0.0))
        close = float(candle["close"])
        open_price = float(candle.get("open", close))
        weight = 3 if (prev_volume is not None and volume > prev_volume) else 1
        if close > open_price:
            score += weight
        elif close < open_price:
            score -= weight
        prev_volume = volume
    return score


def _mat_inv(a):
    """Inverse d'une petite matrice carrée par Gauss-Jordan. Pur."""
    n = len(a)
    m = [list(row) + [1.0 if i == j else 0.0 for j in range(n)] for i, row in enumerate(a)]
    for col in range(n):
        piv = max(range(col, n), key=lambda r: abs(m[r][col]))
        if abs(m[piv][col]) < 1e-12:
            raise ValueError("matrice singulière")
        m[col], m[piv] = m[piv], m[col]
        pv = m[col][col]
        m[col] = [x / pv for x in m[col]]
        for r in range(n):
            if r != col:
                f = m[r][col]
                m[r] = [x - f * y for x, y in zip(m[r], m[col])]
    return [row[n:] for row in m]


def savitzky_golay(values, window=11, poly=2):
    """Lissage Savitzky–Golay (ajuste un polynôme local par moindres carrés). Pur.

    Réduit le bruit haute fréquence tout en préservant les tendances/courbures —
    le levier de débruitage le plus efficace pour les features de microstructure
    (cf. arXiv:2506.05764). Longueur préservée ; bords gérés par réplication.
    Retombe sur l'entrée si la fenêtre est trop courte. SAFE : calcul pur.
    """
    values = [float(v) for v in values]
    n = len(values)
    if n == 0:
        return []
    if window % 2 == 0:
        window += 1
    if window > n:
        window = n if n % 2 else n - 1
    if window < 3 or poly >= window:
        return list(values)
    m = window // 2
    A = [[float(j ** k) for k in range(poly + 1)] for j in range(-m, m + 1)]
    ata = [[sum(A[r][i] * A[r][j] for r in range(len(A))) for j in range(poly + 1)]
           for i in range(poly + 1)]
    inv = _mat_inv(ata)
    # poids de lissage du point central = ligne 0 de (AᵀA)⁻¹Aᵀ
    weights = [sum(inv[0][k] * A[j][k] for k in range(poly + 1)) for j in range(len(A))]
    out = []
    for i in range(n):
        acc = 0.0
        for off in range(-m, m + 1):
            idx = min(max(i + off, 0), n - 1)        # réplication des bords
            acc += weights[off + m] * values[idx]
        out.append(acc)
    return out
