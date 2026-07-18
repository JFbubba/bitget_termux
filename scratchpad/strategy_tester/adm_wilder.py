"""ADM / système directionnel de Wilder — implémentation FIDÈLE en MACHINE À ÉTATS.

Corrige l'erreur de `adm_strategy.py` (conditions évaluées SIMULTANÉMENT à la barre du
croisement → auto-contradiction artificielle). Ici les 3 règles de Wilder INTERAGISSENT
dans le temps (*New Concepts in Technical Trading Systems*, J. W. Wilder) :

  1. CROSSOVER RULE  : +DI croise -DI → ARME un signal directionnel (n'entre PAS).
  2. EXTREME POINT RULE : on note le point extrême de la barre de croisement
       (high pour un long, low pour un short) ; on n'ENTRE que lorsqu'une barre
       ULTÉRIEURE franchit ce point extrême. (anti-whipsaw + laisse l'ADX se retourner).
  3. ADX = PORTE DE RÉGIME (retardé, pas timing) : filtre ADX>seuil [et montant]
       vérifié AU MOMENT DE L'ENTRÉE (franchissement), pas à la barre du croisement.

Système stop-and-reverse : au croisement inverse on arme le signal opposé ; l'entrée
inverse (franchissement du point extrême opposé) FERME et RENVERSE la position.

Contrat engine.py : décision causale à la clôture de t, fill à l'ouverture de t+1.
L'état d'armement PERSISTE entre les barres (closure) — le moteur appelle la stratégie
une fois par barre dans l'ordre chronologique.
"""
from __future__ import annotations
import numpy as np
from adm_strategy import wilder_dmi, ema_full   # indicateurs Wilder (numpy pur, déjà validés)


def make_adm_wilder(ohlcv, period=14, adx_min=25.0, atr_mult=2.0,
                    use_ema200=True, ema_span=200, require_rising=True,
                    arm_window=None, reverse=True, exit_adx_drop=False, adx_drop_n=3,
                    entry_trigger="extreme"):
    """entry_trigger : 'extreme' = règle de Wilder (franchir le point extrême) ;
                       'immediate' = entrer dès le croisement (l'ANCIEN modèle fautif,
                       fourni pour mesurer l'écart imputable à la correction).
       arm_window     : nb max de barres où un signal reste armé (None = jusqu'au
                        croisement inverse).
       reverse        : True = stop-and-reverse de Wilder ; False = sortie vers flat.
    """
    h = np.asarray(ohlcv["h"], float)
    l = np.asarray(ohlcv["l"], float)
    c = np.asarray(ohlcv["c"], float)
    pDI, mDI, adx, atr = wilder_dmi(h, l, c, period)
    ema = ema_full(c, ema_span) if use_ema200 else None

    # --- état d'armement persistant (Extreme Point Rule) ---
    armed = {"side": 0, "extreme": np.nan, "bar": -1}  # side: +1 long / -1 short / 0 aucun

    def _ready(i):
        if i < 3:
            return False
        vals = [pDI[i], mDI[i], adx[i], adx[i - 1], atr[i], c[i]]
        if use_ema200:
            vals.append(ema[i])
        return all(np.isfinite(v) for v in vals)

    def _cross_bull(i):
        return pDI[i] > mDI[i] and pDI[i - 1] <= mDI[i - 1]

    def _cross_bear(i):
        return mDI[i] > pDI[i] and mDI[i - 1] <= pDI[i - 1]

    def _adx_gate(i):
        strong = adx[i] > adx_min
        rising = (adx[i] > adx[i - 1]) if require_rising else True
        return strong and rising

    def _adx_falling(i):
        if not exit_adx_drop or i < adx_drop_n:
            return False
        seq = adx[i - adx_drop_n:i + 1]
        if any(not np.isfinite(v) for v in seq):
            return False
        return all(seq[k] < seq[k - 1] for k in range(1, len(seq)))

    def _sl(i):
        return atr_mult * atr[i] / c[i]

    def _entry_fires(i, side):
        """Le prix franchit-il le point extrême dans le bon sens à la clôture de t ?"""
        if entry_trigger == "immediate":
            return True                      # ancien modèle : entrée au croisement même
        if side == 1:
            return c[i] > armed["extreme"]   # franchit le high du croisement (long)
        return c[i] < armed["extreme"]       # franchit le low du croisement (short)

    def _trend_ok(i, side):
        if not use_ema200:
            return True
        return c[i] > ema[i] if side == 1 else c[i] < ema[i]

    def adm(ctx):
        i = ctx["i"]
        pos = ctx["position"]
        if not _ready(i):
            return {"signal": 0} if pos == 0 else {"signal": None}

        # 1. CROSSOVER RULE : (ré)armer le signal + point extrême
        if _cross_bull(i):
            armed.update(side=1, extreme=h[i], bar=i)
        elif _cross_bear(i):
            armed.update(side=-1, extreme=l[i], bar=i)
        # expiration éventuelle de l'armement
        if arm_window is not None and armed["side"] != 0 and i - armed["bar"] > arm_window:
            armed.update(side=0, extreme=np.nan, bar=-1)

        s = armed["side"]

        # 2. EXTREME POINT RULE + ADX-gate au moment de l'ENTRÉE
        def _armed_entry_signal():
            if s == 1 and _entry_fires(i, 1) and _adx_gate(i) and _trend_ok(i, 1):
                return 1
            if s == -1 and _entry_fires(i, -1) and _adx_gate(i) and _trend_ok(i, -1):
                return -1
            return 0

        if pos == 0:
            sig = _armed_entry_signal()
            if sig != 0:
                armed.update(side=0, extreme=np.nan, bar=-1)   # consommé
                return {"signal": sig, "sl": _sl(i)}
            return {"signal": 0}

        # en position : sortie/reverse
        want_reverse = _armed_entry_signal()          # armement opposé franchi ?
        if pos == 1:
            if reverse and want_reverse == -1:
                armed.update(side=0, extreme=np.nan, bar=-1)
                return {"signal": -1, "sl": _sl(i)}   # ferme long + ouvre short
            if _adx_falling(i) or (not reverse and _cross_bear(i)):
                return {"signal": 0}
            return {"signal": None}
        # pos == -1
        if reverse and want_reverse == 1:
            armed.update(side=0, extreme=np.nan, bar=-1)
            return {"signal": 1, "sl": _sl(i)}
        if _adx_falling(i) or (not reverse and _cross_bull(i)):
            return {"signal": 0}
        return {"signal": None}

    return adm
