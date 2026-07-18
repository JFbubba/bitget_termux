"""SMC / ICT en MACHINE À ÉTATS CAUSALE — pour re-tester correctement (audit ERR-014).

Le rejet passé de SMC reposait sur une checklist de confluence CONTEMPORAINE à la
dernière barre (`smc.analyze()`), pas sur la SÉQUENCE ICT rejouée dans le temps. On la
rejoue ici comme un vrai système à états, sur le contrat de engine.py.

⚠️ CAUSALITÉ STRICTE (sinon on fabrique un faux edge par look-ahead, l'inverse d'ERR-014) :
les primitives de smc.py ont du look-ahead (swing fractale confirmé à +2 barres ; FVG
marqués `filled` en regardant le FUTUR). Ici tout est recalculé en UNE passe chronologique :
- un swing centré en j n'est CONNU (confirmé) qu'à la barre j+2 ;
- un FVG est jugé sur ses 3 bougies seulement (t-2,t-1,t), jamais sur le futur ;
- aucune décision à la barre i n'utilise une donnée d'indice > i.

Séquence (long ; miroir pour short) :
  1. SWEEP sell-side : low[i] perce SOUS un swing-low confirmé, close[i] AU-DESSUS (stop hunt).
  2. Swing-high RESPONSABLE = dernier swing-high confirmé avant le swing-low balayé = niveau à casser.
  3. CHoCH : une bougie clôture EN CORPS (ratio ≥ body_min) au-dessus du niveau (displacement).
  4. FVG haussier au displacement → zone d'ENTRÉE ; STOP = plus bas du sweep (structurel).
  5. ENTRÉE décalée : quand une barre ULTÉRIEURE revient dans le FVG (retest). TP = rr × risque.
     Sortie aussi sur CHoCH inverse (setup opposé) ou par SL/TP intrabar du moteur.
"""
from __future__ import annotations
import numpy as np


def _atr_series(h, l, c, period=14):
    n = len(c)
    tr = np.full(n, np.nan)
    tr[1:] = np.maximum.reduce([h[1:] - l[1:], np.abs(h[1:] - c[:-1]), np.abs(l[1:] - c[:-1])])
    atr = np.full(n, np.nan)
    if n > period:
        atr[period] = np.nanmean(tr[1:period + 1])
        for i in range(period + 1, n):
            atr[i] = atr[i - 1] + (tr[i] - atr[i - 1]) / period
    return atr


def precompute_setups(h, l, c, o, body_min=0.5, fvg_atr_mult=0.3,
                      lookback_swings=12, pending_window=15):
    """Passe chronologique CAUSALE → liste de setups {side, idx, fvg_top, fvg_bot, stop}
    triée par idx. `idx` = barre du CHoCH (= 1ʳᵉ barre où le setup est connu)."""
    n = len(c)
    atr = _atr_series(h, l, c)
    conf_low, conf_high = [], []          # (center, price) confirmés
    pend_long = pend_short = None
    setups = []

    def body_ratio(i):
        rng = h[i] - l[i]
        return abs(c[i] - o[i]) / rng if rng > 0 else 0.0

    for i in range(n):
        # 1. confirmer le swing centré en j = i-2 (fractale 5 barres, connu seulement à i)
        j = i - 2
        if j >= 2:
            if h[j] > h[j - 1] and h[j] > h[j - 2] and h[j] > h[j + 1] and h[j] > h[j + 2]:
                conf_high.append((j, h[j]))
            if l[j] < l[j - 1] and l[j] < l[j - 2] and l[j] < l[j + 1] and l[j] < l[j + 2]:
                conf_low.append((j, l[j]))

        # 2. détecter un SWEEP à i sur les swings confirmés récents
        for cj, lv in reversed(conf_low[-lookback_swings:]):
            if cj < i and l[i] < lv < c[i]:
                resp = [hp for hc, hp in conf_high if hc < cj]
                if resp:
                    pend_long = {"level": resp[-1], "stop": l[i], "t0": i}
                break
        for cj, hv in reversed(conf_high[-lookback_swings:]):
            if cj < i and h[i] > hv > c[i]:
                resp = [lp for lc, lp in conf_low if lc < cj]
                if resp:
                    pend_short = {"level": resp[-1], "stop": h[i], "t0": i}
                break

        # 3+4. CHoCH confirmant le sweep en attente + FVG au displacement
        if pend_long is not None:
            if c[i] > pend_long["level"] and body_ratio(i) >= body_min:
                if i >= 2 and l[i] > h[i - 2] and (l[i] - h[i - 2]) >= (atr[i] or 0) * fvg_atr_mult:
                    rng_hi = float(np.max(h[pend_long["t0"]:i + 1]))   # haut du range d'impulsion
                    setups.append({"side": 1, "idx": i, "fvg_top": l[i], "fvg_bot": h[i - 2],
                                   "stop": pend_long["stop"], "target": rng_hi,
                                   "range_lo": pend_long["stop"], "range_hi": rng_hi})
                pend_long = None
            elif i - pend_long["t0"] > pending_window:
                pend_long = None
        if pend_short is not None:
            if c[i] < pend_short["level"] and body_ratio(i) >= body_min:
                if i >= 2 and h[i] < l[i - 2] and (l[i - 2] - h[i]) >= (atr[i] or 0) * fvg_atr_mult:
                    rng_lo = float(np.min(l[pend_short["t0"]:i + 1]))   # bas du range d'impulsion
                    setups.append({"side": -1, "idx": i, "fvg_top": l[i - 2], "fvg_bot": h[i],
                                   "stop": pend_short["stop"], "target": rng_lo,
                                   "range_lo": rng_lo, "range_hi": pend_short["stop"]})
                pend_short = None
            elif i - pend_short["t0"] > pending_window:
                pend_short = None

    return setups


def make_smc_ict(ohlcv, body_min=0.5, fvg_atr_mult=0.3, rr=2.0, arm_window=20,
                 lookback_swings=12, pending_window=15, exit_on_opposite=True,
                 structural_target=True, entry_depth=0.62):
    """entry_depth : profondeur du RETRACEMENT (OTE) dans le dealing range avant d'entrer.
       0.5 = équilibre ; 0.62-0.79 = zone OTE (discount pour long / premium pour short).
       C'est le vrai déclencheur ICT (retracement→discount→entrée), pas le FVG du displacement."""
    h = np.asarray(ohlcv["h"], float); l = np.asarray(ohlcv["l"], float)
    c = np.asarray(ohlcv["c"], float); o = np.asarray(ohlcv["o"], float)
    setups = precompute_setups(h, l, c, o, body_min, fvg_atr_mult, lookback_swings, pending_window)
    st = {"ptr": 0, "armed": None}

    def strat(ctx):
        i = ctx["i"]; pos = ctx["position"]
        # armer avec le setup le plus récent connu à <= i (nouvelle structure supplante l'ancienne)
        fresh = False
        while st["ptr"] < len(setups) and setups[st["ptr"]]["idx"] <= i:
            st["armed"] = setups[st["ptr"]]; st["ptr"] += 1
            fresh = (st["armed"]["idx"] == i)
        a = st["armed"]
        if a is not None and i - a["idx"] > arm_window:
            a = st["armed"] = None

        if pos != 0:                                   # en position : sortie sur CHoCH inverse
            if exit_on_opposite and fresh and a is not None and a["side"] != pos:
                return {"signal": 0}
            return {"signal": None}

        if a is None:
            return {"signal": 0}
        side = a["side"]
        rng = a["range_hi"] - a["range_lo"]
        if side == 1:
            if c[i] <= a["stop"]:                        # invalidé (retracement casse le bas du range)
                st["armed"] = None; return {"signal": 0}
            entry_level = a["range_hi"] - entry_depth * rng   # zone d'entrée OTE (discount)
            if l[i] <= entry_level:                     # le prix a retracé dans le discount
                entry = c[i]
                st["armed"] = None
                sl = (entry - a["stop"]) / entry
                if sl <= 0:
                    return {"signal": 0}
                tp = (a["target"] - entry) / entry if (structural_target and a["target"] > entry) else rr * sl
                return {"signal": 1, "sl": sl, "tp": tp}
        else:
            if c[i] >= a["stop"]:
                st["armed"] = None; return {"signal": 0}
            entry_level = a["range_lo"] + entry_depth * rng   # zone d'entrée OTE (premium)
            if h[i] >= entry_level:
                entry = c[i]
                st["armed"] = None
                sl = (a["stop"] - entry) / entry
                if sl <= 0:
                    return {"signal": 0}
                tp = (entry - a["target"]) / entry if (structural_target and a["target"] < entry) else rr * sl
                return {"signal": -1, "sl": sl, "tp": tp}
        return {"signal": 0}

    return strat
