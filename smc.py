"""
smc.py — moteur Smart Money Concepts (ICT) : analyse pure, LECTURE SEULE.

Classement : SAFE. Données OHLCV publiques uniquement, AUCUN ordre, aucun secret,
aucune écriture de trading. Ce module ne passe RIEN : il traduit les concepts SMC
(décrits dans docs/ et le dépôt JFbubba/smc) en booléens/zones déterministes pour
la VISUALISATION du dashboard et une lecture de setup PAPER.

⚠️ Il n'est PAS branché dans le banc des 14 agents (GELÉ, §62) ni dans `guards()` :
c'est une surcouche d'observation. Aucune sortie d'ici ne desserre un mur argent,
ne modifie le sizing réel, ni ne déclenche d'exécution. Le `setup` renvoyé par
`analyze()` est un PLAN indicatif (paper), jamais un ordre.

Concepts modélisés (voir README du dépôt SMC) :
  - Fair Value Gap (FVG) : inefficacité sur 3 bougies, filtrée par ATR.
  - Swings (fractales de Bill Williams, 5 bougies).
  - Liquidity Sweep : balayage d'un swing (stop-hunt) puis réintégration.
  - Change of Character (ChoCh) valide : sweep -> cassure en corps du swing
    responsable -> déplacement (corps ≥60 %) laissant un FVG.
  - Balanced Price Range (BPR) : deux FVG opposés qui se superposent.
  - Kill Zones / Silver Bullet : fenêtres horaires (heure de New York).
  - Power of Three (AMD) : accumulation / manipulation / distribution autour
    du Midnight Open.
  - SMT Divergence : rupture de corrélation entre deux actifs.

Format d'entrée des bougies : liste, chaque bougie étant
  - une liste  [ts_sec, open, high, low, close, volume]  (format dashboard), ou
  - un dict    {"time"/"ts", "open", "high", "low", "close", "volume"/"volume_base"}.
Triées par temps CROISSANT. Le temps est en secondes epoch (UTC).

CLI : python smc.py [SYMBOL] [granularity]   (ex. python smc.py BTCUSDT 15m)
"""

from datetime import datetime, timezone

# Fenêtres horaires SMC — heure de New York (America/New_York, EST/EDT géré par zoneinfo).
KILL_ZONES = {
    "asian": (20, 24),    # 20h00 -> 00h00 : consolidation, on marque les extrêmes
    "london": (2, 5),     # 02h00 -> 05h00 : manipulation (Judas swing du PO3)
    "newyork": (7, 10),   # 07h00 -> 10h00 : expansion
}
# Fenêtres Silver Bullet (heure de New York) : 1 h chacune.
SILVER_BULLET = ((3, 4), (10, 11), (14, 15))


# --------------------------------------------------------------------------- #
#  Normalisation                                                              #
# --------------------------------------------------------------------------- #
def _rows(candles):
    """Normalise en liste de tuples (ts, o, h, l, c, v). Best-effort, robuste."""
    out = []
    for k in candles or []:
        try:
            if isinstance(k, dict):
                ts = k.get("ts", k.get("time"))
                if hasattr(ts, "timestamp"):      # datetime -> epoch secondes
                    ts = ts.timestamp()
                ts = float(ts)
                if ts > 1e11:                      # millisecondes -> secondes
                    ts /= 1000.0
                vol = k.get("volume", k.get("volume_base", 0.0))
                out.append((ts, float(k["open"]), float(k["high"]),
                            float(k["low"]), float(k["close"]), float(vol or 0.0)))
            else:
                ts = float(k[0])
                if ts > 1e11:
                    ts /= 1000.0
                out.append((ts, float(k[1]), float(k[2]), float(k[3]),
                            float(k[4]), float(k[5]) if len(k) > 5 else 0.0))
        except (TypeError, ValueError, KeyError, IndexError):
            continue
    return out


# indices lisibles dans un tuple de bougie
_TS, _O, _H, _L, _C, _V = range(6)


def _atr(rows, period=14):
    """ATR simple (moyenne des True Range). 0.0 si trop court."""
    if len(rows) < 2:
        return 0.0
    trs = []
    for i in range(1, len(rows)):
        h, l, pc = rows[i][_H], rows[i][_L], rows[i - 1][_C]
        trs.append(max(h - l, abs(h - pc), abs(l - pc)))
    window = trs[-period:] if len(trs) >= period else trs
    return sum(window) / len(window) if window else 0.0


# --------------------------------------------------------------------------- #
#  Fair Value Gaps                                                            #
# --------------------------------------------------------------------------- #
def fair_value_gaps(candles, atr_mult=0.5, keep_filled=False):
    """FVG sur 3 bougies (t-2, t-1, t), filtrés par taille (ATR14 × atr_mult).

    Bullish FVG : low[t] > high[t-2]  (trou haussier).
    Bearish FVG : high[t] < low[t-2]  (trou baissier).
    Un FVG est « mitigé/filled » si une bougie POSTÉRIEURE réintègre le trou.
    Renvoie une liste de dicts {type, top, bottom, entry, invalidation, ts, index, filled}.
    """
    rows = _rows(candles)
    n = len(rows)
    if n < 3:
        return []
    atr = _atr(rows) or 0.0
    min_size = atr * atr_mult
    gaps = []
    for t in range(2, n):
        c2, c1, c0 = rows[t - 2], rows[t - 1], rows[t]
        # Bullish FVG
        if c0[_L] > c2[_H]:
            size = c0[_L] - c2[_H]
            if size >= min_size:
                gaps.append({"type": "bull", "top": c0[_L], "bottom": c2[_H],
                             "entry": c2[_H], "invalidation": c1[_L],
                             "ts": c0[_TS], "index": t, "size": size})
        # Bearish FVG
        elif c0[_H] < c2[_L]:
            size = c2[_L] - c0[_H]
            if size >= min_size:
                gaps.append({"type": "bear", "top": c2[_L], "bottom": c0[_H],
                             "entry": c2[_L], "invalidation": c1[_H],
                             "ts": c0[_TS], "index": t, "size": size})
    # marque le remplissage (une bougie ultérieure retourne DANS le trou)
    for g in gaps:
        g["filled"] = False
        for j in range(g["index"] + 1, n):
            if g["type"] == "bull" and rows[j][_L] <= g["bottom"]:
                g["filled"] = True
                break
            if g["type"] == "bear" and rows[j][_H] >= g["top"]:
                g["filled"] = True
                break
    if not keep_filled:
        gaps = [g for g in gaps if not g["filled"]]
    return gaps


# --------------------------------------------------------------------------- #
#  Swings (fractales de Bill Williams, 5 bougies)                            #
# --------------------------------------------------------------------------- #
def swings(candles):
    """Swing High / Low par fractale à 5 bougies (2 de chaque côté du centre).

    SwingHigh en i : high[i] > high[i±1] et high[i±2].
    SwingLow  en i : low[i]  < low[i±1]  et low[i±2].
    Renvoie une liste triée {index, ts, price, type: 'high'|'low'}.
    """
    rows = _rows(candles)
    n = len(rows)
    out = []
    for i in range(2, n - 2):
        h = rows[i][_H]
        if h > rows[i - 1][_H] and h > rows[i - 2][_H] and h > rows[i + 1][_H] and h > rows[i + 2][_H]:
            out.append({"index": i, "ts": rows[i][_TS], "price": h, "type": "high"})
        l = rows[i][_L]
        if l < rows[i - 1][_L] and l < rows[i - 2][_L] and l < rows[i + 1][_L] and l < rows[i + 2][_L]:
            out.append({"index": i, "ts": rows[i][_TS], "price": l, "type": "low"})
    out.sort(key=lambda s: s["index"])
    return out


# --------------------------------------------------------------------------- #
#  Liquidity Sweeps                                                          #
# --------------------------------------------------------------------------- #
def liquidity_sweeps(candles, sw=None):
    """Balayages de liquidité : une bougie perce un swing puis le réintègre (close).

    - sell-side (biais haussier) : low perce SOUS un SwingLow, close AU-DESSUS.
    - buy-side  (biais baissier) : high perce AU-DESSUS d'un SwingHigh, close EN-DESSOUS.
    Renvoie {index, ts, side: 'sell'|'buy', level, swing_index}.
    """
    rows = _rows(candles)
    sw = sw if sw is not None else swings(candles)
    lows = [s for s in sw if s["type"] == "low"]
    highs = [s for s in sw if s["type"] == "high"]
    out = []
    for i, r in enumerate(rows):
        for s in lows:
            if s["index"] < i and r[_L] < s["price"] and r[_C] > s["price"]:
                out.append({"index": i, "ts": r[_TS], "side": "sell",
                            "level": s["price"], "swing_index": s["index"]})
                break
        for s in highs:
            if s["index"] < i and r[_H] > s["price"] and r[_C] < s["price"]:
                out.append({"index": i, "ts": r[_TS], "side": "buy",
                            "level": s["price"], "swing_index": s["index"]})
                break
    return out


def _body_ratio(row):
    rng = row[_H] - row[_L]
    return abs(row[_C] - row[_O]) / rng if rng > 0 else 0.0


# --------------------------------------------------------------------------- #
#  Change of Character (ChoCh) valide                                        #
# --------------------------------------------------------------------------- #
def change_of_character(candles, sw=None, body_min=0.6):
    """ChoCh institutionnel valide selon les 3 règles d'or (README §ChoCh) :

    Séquence haussière stricte :
      1. Balayage d'un SwingLow (sell-side liquidity sweep) = carburant.
      2. Le SwingHigh responsable (dernier swing high AVANT le low balayé) devient
         le `level` à casser.
      3. Une bougie clôture EN CORPS au-dessus du level (displacement), corps ≥ body_min.
      4. Cette impulsion laisse un FVG haussier (empreinte institutionnelle).
    Miroir pour le ChoCh baissier. Renvoie {index, ts, type, level, entry_fvg, valid}.
    """
    rows = _rows(candles)
    sw = sw if sw is not None else swings(candles)
    fvgs = fair_value_gaps(candles, keep_filled=True)
    fvg_by_index = {}
    for g in fvgs:                                   # dernier FVG connu à/avant chaque t
        fvg_by_index.setdefault(g["type"], []).append(g)
    sweeps = liquidity_sweeps(candles, sw)
    highs = [s for s in sw if s["type"] == "high"]
    lows = [s for s in sw if s["type"] == "low"]
    out = []
    n = len(rows)
    for swp in sweeps:
        if swp["side"] == "sell":                    # -> cherche un ChoCh haussier
            # SwingHigh responsable : dernier swing high avant le swing low balayé
            resp = [h for h in highs if h["index"] < swp["swing_index"]]
            if not resp:
                continue
            level = resp[-1]["price"]
            for t in range(swp["index"], n):
                if rows[t][_C] > level and _body_ratio(rows[t]) >= body_min:
                    fvg = next((g for g in fvg_by_index.get("bull", [])
                                if swp["index"] <= g["index"] <= t + 1 and not g["filled"]), None)
                    out.append({"index": t, "ts": rows[t][_TS], "type": "bullish",
                                "level": level, "displacement": round(_body_ratio(rows[t]), 3),
                                "entry_fvg": fvg, "valid": fvg is not None,
                                "sweep_level": swp["level"], "sweep_index": swp["index"]})
                    break
        else:                                        # -> cherche un ChoCh baissier
            resp = [l for l in lows if l["index"] < swp["swing_index"]]
            if not resp:
                continue
            level = resp[-1]["price"]
            for t in range(swp["index"], n):
                if rows[t][_C] < level and _body_ratio(rows[t]) >= body_min:
                    fvg = next((g for g in fvg_by_index.get("bear", [])
                                if swp["index"] <= g["index"] <= t + 1 and not g["filled"]), None)
                    out.append({"index": t, "ts": rows[t][_TS], "type": "bearish",
                                "level": level, "displacement": round(_body_ratio(rows[t]), 3),
                                "entry_fvg": fvg, "valid": fvg is not None,
                                "sweep_level": swp["level"], "sweep_index": swp["index"]})
                    break
    out.sort(key=lambda c: c["index"])
    return out


# --------------------------------------------------------------------------- #
#  Balanced Price Range (BPR)                                                #
# --------------------------------------------------------------------------- #
def balanced_price_ranges(candles, fvgs=None):
    """BPR : superposition d'un FVG haussier et d'un FVG baissier (zone équilibrée
    qui agit ensuite comme un mur). Renvoie {top, bottom, ts, index}."""
    gaps = fvgs if fvgs is not None else fair_value_gaps(candles, keep_filled=True)
    bulls = [g for g in gaps if g["type"] == "bull"]
    bears = [g for g in gaps if g["type"] == "bear"]
    out = []
    for b in bulls:
        for s in bears:
            if abs(b["index"] - s["index"]) > 6:
                continue
            top = min(b["top"], s["top"])
            bottom = max(b["bottom"], s["bottom"])
            if top > bottom:                          # les deux trous se recouvrent
                out.append({"top": top, "bottom": bottom,
                            "ts": max(b["ts"], s["ts"]),
                            "index": max(b["index"], s["index"])})
    # dédoublonne les zones quasi identiques
    uniq = []
    for z in sorted(out, key=lambda x: x["index"]):
        if not any(abs(z["top"] - u["top"]) < 1e-9 and abs(z["bottom"] - u["bottom"]) < 1e-9 for u in uniq):
            uniq.append(z)
    return uniq


# --------------------------------------------------------------------------- #
#  OTE — Optimal Trade Entry (retracement Fibonacci de la jambe de displacement) #
# --------------------------------------------------------------------------- #
def ote_zone(leg_low, leg_high, direction, lo_r=0.62, hi_r=0.79, sweet_r=0.705):
    """Zone OTE = retracement Fibonacci de la JAMBE de displacement (sweep -> ChoCh).

    LONG : jambe du bas balayé (`leg_low`) au sommet du displacement (`leg_high`) ; l'entrée
    idéale est un RETOUR dans 0.62–0.79 (sweet 0.705), SOUS l'équilibre 0.5 (zone « discount »).
    SHORT : miroir (jambe haut->bas, retour 0.62–0.79 au-dessus de l'équilibre = « premium »).
    Retourne {lo, hi, sweet, eq, direction} en PRIX, ou None si jambe dégénérée. PUR &
    look-ahead-free : la jambe est déjà entièrement formée au ChoCh (bornes ≤ index du ChoCh)."""
    rng = leg_high - leg_low
    if rng <= 0:
        return None
    if direction == "LONG":                     # retour vers le BAS depuis le sommet
        return {"lo": leg_high - hi_r * rng, "hi": leg_high - lo_r * rng,
                "sweet": leg_high - sweet_r * rng, "eq": leg_high - 0.5 * rng,
                "direction": "LONG"}
    return {"lo": leg_low + lo_r * rng, "hi": leg_low + hi_r * rng,   # retour vers le HAUT
            "sweet": leg_low + sweet_r * rng, "eq": leg_low + 0.5 * rng,
            "direction": "SHORT"}


# --------------------------------------------------------------------------- #
#  Kill Zones / Silver Bullet / Power of Three (heure de New York)           #
# --------------------------------------------------------------------------- #
def _ny(dt):
    """Convertit un datetime (UTC) vers l'heure de New York. Repli statique UTC-4
    si zoneinfo indisponible."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    try:
        from zoneinfo import ZoneInfo
        return dt.astimezone(ZoneInfo("America/New_York"))
    except Exception:
        from datetime import timedelta
        return dt.astimezone(timezone.utc) - timedelta(hours=4)


def kill_zone(dt=None):
    """Statut horaire SMC à l'instant `dt` (UTC, défaut = maintenant).
    Renvoie {ny_hour, zone: asian|london|newyork|None, silver_bullet: bool, tradeable: bool}."""
    dt = dt or datetime.now(timezone.utc)
    ny = _ny(dt)
    h = ny.hour
    zone = None
    for name, (a, b) in KILL_ZONES.items():
        if a <= h < b or (b == 24 and h >= a):
            zone = name
            break
    sb = any(a <= h < b for a, b in SILVER_BULLET)
    return {"ny_hour": h, "ny_time": ny.strftime("%H:%M"), "zone": zone,
            "silver_bullet": sb, "tradeable": zone in ("london", "newyork")}


def power_of_three(candles):
    """Power of Three (AMD) autour du Midnight Open (00:00 New York).

    Renvoie {midnight_open, phase: accumulation|manipulation|distribution|None,
    discount: bool, premium: bool, last_close}. Le Midnight Open est le repère :
    biais haussier -> on ne cherche des achats que SOUS ce prix (zone discount)."""
    rows = _rows(candles)
    if not rows:
        return {}
    # trouve la première bougie du jour NY courant (>= minuit NY)
    last_ny = _ny(datetime.fromtimestamp(rows[-1][_TS], tz=timezone.utc))
    midnight_open = None
    mid_idx = None
    for i, r in enumerate(rows):
        ny = _ny(datetime.fromtimestamp(r[_TS], tz=timezone.utc))
        if ny.date() == last_ny.date():
            midnight_open = r[_O]
            mid_idx = i
            break
    if midnight_open is None:
        return {"midnight_open": None, "phase": None}
    last_close = rows[-1][_C]
    kz = kill_zone(datetime.fromtimestamp(rows[-1][_TS], tz=timezone.utc))
    if kz["zone"] == "london":
        phase = "manipulation"
    elif kz["zone"] == "newyork":
        phase = "distribution"
    elif kz["zone"] == "asian":
        phase = "accumulation"
    else:
        phase = None
    return {"midnight_open": round(midnight_open, 6), "phase": phase,
            "discount": last_close < midnight_open, "premium": last_close > midnight_open,
            "last_close": round(last_close, 6), "candles_since_open": len(rows) - (mid_idx or 0)}


def session_levels(candles):
    """Niveaux de référence SMC disponibles dans la fenêtre : Asian High/Low de la
    dernière session asiatique + Previous Day High/Low (bornes de jour NY).
    Best-effort selon la profondeur/TF fournie."""
    rows = _rows(candles)
    if not rows:
        return {}
    last_ny = _ny(datetime.fromtimestamp(rows[-1][_TS], tz=timezone.utc))
    today = last_ny.date()
    asian_h = asian_l = None
    pdh = pdl = None
    for r in rows:
        ny = _ny(datetime.fromtimestamp(r[_TS], tz=timezone.utc))
        # session asiatique = 20h->24h NY (veille) : appartient au "jour de trading" courant
        if ny.hour >= 20 and (today - ny.date()).days in (0, 1):
            asian_h = r[_H] if asian_h is None else max(asian_h, r[_H])
            asian_l = r[_L] if asian_l is None else min(asian_l, r[_L])
        if (today - ny.date()).days == 1:             # jour NY précédent
            pdh = r[_H] if pdh is None else max(pdh, r[_H])
            pdl = r[_L] if pdl is None else min(pdl, r[_L])
    out = {}
    if asian_h is not None:
        out["asian_high"] = round(asian_h, 6)
        out["asian_low"] = round(asian_l, 6)
    if pdh is not None:
        out["prev_day_high"] = round(pdh, 6)
        out["prev_day_low"] = round(pdl, 6)
    return out


# --------------------------------------------------------------------------- #
#  SMT Divergence (deux actifs corrélés)                                     #
# --------------------------------------------------------------------------- #
def smt_divergence(candles_a, candles_b, lookback=20):
    """Divergence SMT : rupture de corrélation entre deux actifs qui bougent
    normalement ensemble (ex. BTC vs ETH). Sur `lookback` dernières bougies :
      - baissière : A fait un Higher High mais B fait un Lower High (distribution).
      - haussière : A fait un Lower Low  mais B fait un Higher Low  (accumulation).
    Renvoie {signal: bullish|bearish|None, detail}. C'est un FILTRE, pas un signal seul."""
    ra, rb = _rows(candles_a)[-lookback:], _rows(candles_b)[-lookback:]
    if len(ra) < 4 or len(rb) < 4:
        return {"signal": None}
    half = min(len(ra), len(rb)) // 2
    a_prev_h, a_last_h = max(r[_H] for r in ra[:half]), max(r[_H] for r in ra[half:])
    b_prev_h, b_last_h = max(r[_H] for r in rb[:half]), max(r[_H] for r in rb[half:])
    a_prev_l, a_last_l = min(r[_L] for r in ra[:half]), min(r[_L] for r in ra[half:])
    b_prev_l, b_last_l = min(r[_L] for r in rb[:half]), min(r[_L] for r in rb[half:])
    if a_last_h > a_prev_h and b_last_h < b_prev_h:
        return {"signal": "bearish", "detail": "A higher-high, B lower-high"}
    if a_last_l < a_prev_l and b_last_l > b_prev_l:
        return {"signal": "bullish", "detail": "A lower-low, B higher-low"}
    return {"signal": None}


# --------------------------------------------------------------------------- #
#  Algorithme d'agrégation : setup PAPER + overlay graphique                 #
# --------------------------------------------------------------------------- #
def analyze(candles, dt=None, candles_smt=None):
    """Agrège tous les concepts SMC en une lecture unique (PAPER, jamais un ordre).

    Suit l'ordre de validation en direct du README :
      1. Kill zone active ? (contexte temporel)
      2. Liquidité balayée récemment ? (carburant)
      3. ChoCh valide (displacement + corps + FVG) ?
      4. FVG d'entrée disponible ?
    Produit un `setup` directionnel indicatif {direction, entry, stop, tp1, tp2},
    un score de confluence 0..4, et un bloc `overlay` prêt pour le graphique
    (zones, niveaux, marqueurs). Ne déclenche AUCUNE exécution.
    """
    rows = _rows(candles)
    if len(rows) < 5:
        return {"ok": False, "reason": "pas assez de bougies"}

    sw = swings(candles)
    fvgs = fair_value_gaps(candles)                    # actifs (non mitigés)
    fvgs_all = fair_value_gaps(candles, keep_filled=True)
    sweeps = liquidity_sweeps(candles, sw)
    chochs = change_of_character(candles, sw)
    bprs = balanced_price_ranges(candles, fvgs_all)
    kz = kill_zone(dt or datetime.fromtimestamp(rows[-1][_TS], tz=timezone.utc))
    po3 = power_of_three(candles)
    levels = session_levels(candles)
    smt = smt_divergence(candles, candles_smt) if candles_smt else {"signal": None}

    n = len(rows)
    recent = max(1, n // 3)                            # « récent » = dernier tiers de la fenêtre
    last_sweep = next((s for s in reversed(sweeps) if s["index"] >= n - recent), None)
    last_choch = next((c for c in reversed(chochs) if c["index"] >= n - recent and c["valid"]), None)

    # --- score de confluence (checklist du README) ---
    checklist = {
        "kill_zone": bool(kz["tradeable"]),
        "sweep": last_sweep is not None,
        "choch_valide": last_choch is not None,
        "fvg_entree": last_choch is not None and last_choch.get("entry_fvg") is not None,
    }
    score = sum(1 for v in checklist.values() if v)

    # --- plan directionnel PAPER (indicatif) ---
    setup = None
    if last_choch and last_choch.get("entry_fvg"):
        fvg = last_choch["entry_fvg"]
        direction = "LONG" if last_choch["type"] == "bullish" else "SHORT"
        entry = fvg["entry"]
        # Stop ancré sur le plus-bas/plus-haut RÉEL du mouvement (du sweep au ChoCh),
        # jamais un niveau lointain incohérent. C'est « juste derrière le point créé
        # par la prise de liquidité » (README).
        lo = last_choch.get("sweep_index", last_choch["index"])
        seg = rows[max(0, lo - 1):last_choch["index"] + 1] or rows[-recent:]
        if direction == "LONG":
            stop = min(r[_L] for r in seg)
            tp1 = levels.get("asian_high") or max(r[_H] for r in rows[-recent:])
            tp2 = levels.get("prev_day_high") or (entry + 2 * abs(entry - stop))
            geo_ok = stop < entry < tp1
        else:
            stop = max(r[_H] for r in seg)
            tp1 = levels.get("asian_low") or min(r[_L] for r in rows[-recent:])
            tp2 = levels.get("prev_day_low") or (entry - 2 * abs(entry - stop))
            geo_ok = tp1 < entry < stop
        risk = abs(entry - stop) or 1e-9
        rr1 = abs(tp1 - entry) / risk
        # OTE : jambe de displacement RÉELLE du sweep au ChoCh (bornes look-ahead-free)
        seg2 = rows[max(0, lo):last_choch["index"] + 1] or rows[-recent:]
        leg_low = min(r[_L] for r in seg2)
        leg_high = max(r[_H] for r in seg2)
        ote = ote_zone(leg_low, leg_high, direction)
        # entrée FVG dans la zone OTE 0.62–0.79 (le raffinement canonique d'entrée) ?
        ote_ok = bool(ote and ote["lo"] - 1e-9 <= entry <= ote["hi"] + 1e-9)
        # cohérence avec Power of Three (achat en discount / vente en premium)
        po3_ok = (direction == "LONG" and po3.get("discount")) or \
                 (direction == "SHORT" and po3.get("premium")) or po3.get("phase") is None
        # filtre SMT : contredit-il la direction ?
        smt_ok = smt["signal"] is None or \
                 (direction == "LONG" and smt["signal"] == "bullish") or \
                 (direction == "SHORT" and smt["signal"] == "bearish")
        setup = {"direction": direction, "entry": round(entry, 6), "stop": round(stop, 6),
                 "tp1": round(tp1, 6), "tp2": round(tp2, 6), "rr1": round(rr1, 2),
                 "po3_aligned": bool(po3_ok), "smt_aligned": bool(smt_ok),
                 "ote_aligned": bool(ote_ok), "silver_bullet": bool(kz.get("silver_bullet")),
                 "ote": ({k: round(v, 6) for k, v in ote.items() if k != "direction"} if ote else None),
                 "coherent": bool(geo_ok),
                 "ready": bool(geo_ok and kz["tradeable"] and score >= 3
                               and po3_ok and smt_ok and ote_ok)}

    bias = "NEUTRE"
    if last_choch:
        bias = "LONG" if last_choch["type"] == "bullish" else "SHORT"
    elif last_sweep:
        bias = "LONG" if last_sweep["side"] == "sell" else "SHORT"

    # --- overlay graphique (zones + niveaux + marqueurs) ---
    overlay = _build_overlay(fvgs, bprs, levels, po3, sweeps, chochs, rows, setup=setup)

    return {
        "ok": True, "bias": bias, "score": score, "checklist": checklist,
        "kill_zone": kz, "power_of_three": po3, "levels": levels, "smt": smt,
        "counts": {"fvg": len(fvgs), "bpr": len(bprs), "swings": len(sw),
                   "sweeps": len(sweeps), "choch": len(chochs)},
        "last_sweep": last_sweep, "last_choch": _light_choch(last_choch),
        "setup": setup, "overlay": overlay,
    }


def _light_choch(c):
    """Version allégée d'un ChoCh pour la sérialisation JSON (drop du FVG imbriqué)."""
    if not c:
        return None
    out = {k: v for k, v in c.items() if k != "entry_fvg"}
    if c.get("entry_fvg"):
        out["fvg_entry"] = round(c["entry_fvg"]["entry"], 6)
    return out


def _build_overlay(fvgs, bprs, levels, po3, sweeps, chochs, rows, setup=None, max_zones=6, max_marks=10):
    """Construit le bloc `overlay` consommé par le front (zones/lignes/marqueurs).
    Ne garde que les éléments récents et non mitigés pour ne pas surcharger le graphique."""
    zones = []
    for g in fvgs[-max_zones:]:
        zones.append({"kind": "fvg", "type": g["type"], "top": round(g["top"], 6),
                      "bottom": round(g["bottom"], 6), "ts": int(g["ts"])})
    for z in bprs[-3:]:
        zones.append({"kind": "bpr", "type": "bpr", "top": round(z["top"], 6),
                      "bottom": round(z["bottom"], 6), "ts": int(z["ts"])})
    # zone OTE (0.62–0.79) du setup courant : la « boîte » d'entrée canonique
    if setup and setup.get("ote"):
        o = setup["ote"]
        zones.append({"kind": "ote", "type": setup["direction"].lower(),
                      "top": round(o["hi"], 6), "bottom": round(o["lo"], 6),
                      "ts": int(rows[-1][_TS])})
    lines = []
    label_map = {"asian_high": "Asian H", "asian_low": "Asian L",
                 "prev_day_high": "PDH", "prev_day_low": "PDL"}
    for key, label in label_map.items():
        if levels.get(key) is not None:
            lines.append({"price": levels[key], "label": label})
    if po3.get("midnight_open") is not None:
        lines.append({"price": po3["midnight_open"], "label": "Midnight Open"})
    if setup and setup.get("ote"):
        lines.append({"price": round(setup["ote"]["sweet"], 6), "label": "OTE 0.705"})
    marks = []
    for s in sweeps[-max_marks:]:
        marks.append({"ts": int(s["ts"]), "kind": "sweep", "side": s["side"],
                      "text": "SWEEP", "price": round(s["level"], 6)})
    for c in chochs[-max_marks:]:
        if c["valid"]:
            marks.append({"ts": int(c["ts"]), "kind": "choch", "side": c["type"],
                          "text": "ChoCh", "price": round(c["level"], 6)})
    return {"zones": zones, "lines": lines, "markers": marks}


# --------------------------------------------------------------------------- #
#  CLI (analyse ad hoc, lecture seule)                                        #
# --------------------------------------------------------------------------- #
def _fetch(symbol, granularity, limit=150):
    import candle_reader
    return candle_reader.get_bitget_candles(symbol, granularity=granularity, limit=limit)


def main():
    import sys
    symbol = sys.argv[1].upper() if len(sys.argv) > 1 else "BTCUSDT"
    granularity = sys.argv[2] if len(sys.argv) > 2 else "15m"
    candles = _fetch(symbol, granularity)
    res = analyze(candles)
    kz = res.get("kill_zone", {})
    print(f"=== SMC {symbol} {granularity} ===")
    print(f"Kill zone : {kz.get('zone') or '—'} (NY {kz.get('ny_time')})"
          f"{' · Silver Bullet' if kz.get('silver_bullet') else ''}"
          f"{' · TRADEABLE' if kz.get('tradeable') else ''}")
    print(f"Biais SMC : {res.get('bias')}  ·  confluence {res.get('score')}/4")
    print(f"Checklist : {res.get('checklist')}")
    print(f"Décompte  : {res.get('counts')}")
    po3 = res.get("power_of_three", {})
    if po3.get("midnight_open"):
        print(f"PO3       : open {po3['midnight_open']} · phase {po3.get('phase')} · "
              f"{'discount' if po3.get('discount') else 'premium'}")
    if res.get("setup"):
        s = res["setup"]
        print(f"SETUP (PAPER) : {s['direction']} entrée {s['entry']} stop {s['stop']} "
              f"TP1 {s['tp1']} TP2 {s['tp2']} · RR1 {s['rr1']} · "
              f"{'PRÊT' if s['ready'] else 'en attente'}")
    else:
        print("SETUP (PAPER) : aucun (pas de ChoCh+FVG récent)")
    print("\nSAFE : analyse seule, aucun ordre passé.")


if __name__ == "__main__":
    main()
