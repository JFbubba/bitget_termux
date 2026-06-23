"""
price_action.py — détecteurs d'action des prix (patterns, structure, FVG). Pur, SAFE.

Issu de l'intake Drive `package/PDF` (Volume Profile, ICT/SMC, chandeliers, Wyckoff).
Le Volume Profile existe déjà (`pro_indicators.volume_profile`) — NON dupliqué ici.
Ce module ajoute ce qui manquait, en fonctions PURES et testables :
  • candlestick_patterns — patterns à la dernière bougie (CONFIRMATEURS, pas signaux).
  • swing_points / market_structure — pivots -> tendance + BOS/CHoCH (SMC).
  • fair_value_gaps — imbalances 3 bougies (FVG haussiers/baissiers).

Règle d'or (cf. RESEARCH_NOTES §10) : un pattern/structure isolé n'a pas d'edge ;
ce sont des CONFIRMATEURS à pondérer par le contexte (Volume Profile, régime,
divergence). Rien n'est un déclencheur unique.
"""


def _body(c):
    return abs(float(c["close"]) - float(c["open"]))


def _rng(c):
    return max(float(c["high"]) - float(c["low"]), 1e-9)


def _upper_wick(c):
    return float(c["high"]) - max(float(c["close"]), float(c["open"]))


def _lower_wick(c):
    return min(float(c["close"]), float(c["open"])) - float(c["low"])


def candlestick_patterns(ohlc):
    """Patterns chandeliers à la DERNIÈRE bougie. Pur.

    Retourne [{name, dir}] avec dir ∈ {+1 haussier, -1 baissier, 0 neutre}.
    Bougies = dict {open, high, low, close}. CONFIRMATEUR, pas signal isolé."""
    if not ohlc:
        return []
    out = []
    c = ohlc[-1]
    body, rng = _body(c), _rng(c)
    up, lo = _upper_wick(c), _lower_wick(c)
    if body <= 0.1 * rng:
        out.append({"name": "doji", "dir": 0})
    if body > 0 and lo >= 2 * body and up <= body:
        out.append({"name": "hammer", "dir": 1})
    if body > 0 and up >= 2 * body and lo <= body:
        out.append({"name": "shooting_star", "dir": -1})
    if len(ohlc) >= 2:
        p = ohlc[-2]
        po, pc = float(p["open"]), float(p["close"])
        co, cc = float(c["open"]), float(c["close"])
        if pc < po and cc > co and cc >= po and co <= pc:
            out.append({"name": "bullish_engulfing", "dir": 1})
        if pc > po and cc < co and co >= pc and cc <= po:
            out.append({"name": "bearish_engulfing", "dir": -1})
    return out


def swing_points(highs, lows, k=2):
    """Pivots fractals : swing high (H) si plus haut que k voisins de chaque côté,
    swing low (L) si plus bas. Retourne [(i, prix, 'H'|'L')] trié par i. Pur."""
    n = min(len(highs), len(lows))
    piv = []
    for i in range(k, n - k):
        if all(highs[i] > highs[i - j] for j in range(1, k + 1)) and \
           all(highs[i] > highs[i + j] for j in range(1, k + 1)):
            piv.append((i, float(highs[i]), "H"))
        if all(lows[i] < lows[i - j] for j in range(1, k + 1)) and \
           all(lows[i] < lows[i + j] for j in range(1, k + 1)):
            piv.append((i, float(lows[i]), "L"))
    piv.sort()
    return piv


def market_structure(highs, lows, closes, k=2):
    """Structure de marché (SMC) : tendance via HH/HL vs LH/LL, et événement
    BOS (continuation) / CHoCH (changement de caractère = retournement). Pur.

    Retourne {trend, bias, event, event_dir, last_swing_high, last_swing_low}."""
    piv = swing_points(highs, lows, k)
    sh = [p for p in piv if p[2] == "H"]
    sl = [p for p in piv if p[2] == "L"]
    trend, bias = "range", 0
    if len(sh) >= 2 and len(sl) >= 2:
        hh, hl = sh[-1][1] > sh[-2][1], sl[-1][1] > sl[-2][1]
        lh, ll = sh[-1][1] < sh[-2][1], sl[-1][1] < sl[-2][1]
        if hh and hl:
            trend, bias = "up", 1
        elif lh and ll:
            trend, bias = "down", -1
    last_sh = sh[-1][1] if sh else None
    last_sl = sl[-1][1] if sl else None
    close = float(closes[-1])
    event, ev_dir = None, 0
    if trend == "up" and last_sl is not None and close < last_sl:
        event, ev_dir = "CHoCH", -1          # cassure du higher-low en up-trend -> reversal
    elif trend == "down" and last_sh is not None and close > last_sh:
        event, ev_dir = "CHoCH", 1
    elif trend == "up" and last_sh is not None and close > last_sh:
        event, ev_dir = "BOS", 1             # continuation haussière
    elif trend == "down" and last_sl is not None and close < last_sl:
        event, ev_dir = "BOS", -1
    return {"trend": trend, "bias": bias, "event": event, "event_dir": ev_dir,
            "last_swing_high": last_sh, "last_swing_low": last_sl}


def fair_value_gaps(candles):
    """Fair Value Gaps (imbalances sur 3 bougies). Pur.

    FVG haussier : high(i-2) < low(i) (vide de prix sous la bougie i = support).
    FVG baissier : low(i-2) > high(i). Retourne [{dir, low, high, i}]."""
    out = []
    for i in range(2, len(candles)):
        a, c = candles[i - 2], candles[i]
        ah, al = float(a["high"]), float(a["low"])
        ch, cl = float(c["high"]), float(c["low"])
        if ah < cl:
            out.append({"dir": 1, "low": ah, "high": cl, "i": i})
        if al > ch:
            out.append({"dir": -1, "low": ch, "high": al, "i": i})
    return out
