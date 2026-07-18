"""Stratégie ADM (Average Directional Movement) — système DMI/ADX de J. W. Wilder.

Réimplémentation FIDÈLE (Wilder smoothing / RMA, comme TA-Lib) en numpy PUR — pas de
TA-Lib/pandas-ta (binaires, ERR-004). Branchée sur le contrat du Strategy Tester
(engine.run_backtest) : décision causale à la clôture de t, fill à l'ouverture de t+1.

Système complet (testé comme un TOUT, ERR-002) :
  Entrée LONG  : +DI croise AU-DESSUS de -DI (croisement FRAIS) ET ADX>seuil ET ADX
                 montant (pente > 0) ET [filtre EMA200 : close > EMA200].
  Entrée SHORT : symétrique.
  Sortie       : croisement inverse des DI  OU  ADX en baisse `adx_drop_n` barres.
  Stop-Loss    : `atr_mult` × ATR(14) (fraction = atr_mult*ATR/close), pas de TP fixe.

Les indicateurs sont pré-calculés UNE fois sur l'ohlcv passé (O(n)) et lus par ctx['i'].
"""
from __future__ import annotations
import numpy as np


# ---------- indicateurs Wilder (numpy pur, causaux) ----------
def _rma(x, period):
    """Moyenne mobile de Wilder (RMA) : seed = SMA des `period` 1ères valeurs finies,
    puis rma[t] = rma[t-1] + (x[t]-rma[t-1])/period. NaN avant le seed."""
    x = np.asarray(x, float)
    n = len(x)
    out = np.full(n, np.nan)
    finite = np.isfinite(x)
    start = None
    for s in range(0, n - period + 1):
        if finite[s:s + period].all():
            start = s
            break
    if start is None:
        return out
    seed_idx = start + period - 1
    out[seed_idx] = float(np.mean(x[start:start + period]))
    for t in range(seed_idx + 1, n):
        xt = x[t] if finite[t] else out[t - 1]
        out[t] = out[t - 1] + (xt - out[t - 1]) / period
    return out


def wilder_dmi(h, l, c, period=14):
    """Retourne (+DI, -DI, ADX, ATR) — définition Wilder exacte."""
    h = np.asarray(h, float); l = np.asarray(l, float); c = np.asarray(c, float)
    n = len(c)
    up = np.full(n, np.nan); dn = np.full(n, np.nan); tr = np.full(n, np.nan)
    up[1:] = h[1:] - h[:-1]
    dn[1:] = l[:-1] - l[1:]
    plus_dm = np.where((up > dn) & (up > 0), up, 0.0)
    minus_dm = np.where((dn > up) & (dn > 0), dn, 0.0)
    plus_dm[0] = np.nan; minus_dm[0] = np.nan
    tr[1:] = np.maximum.reduce([h[1:] - l[1:],
                                np.abs(h[1:] - c[:-1]),
                                np.abs(l[1:] - c[:-1])])
    atr = _rma(tr, period)
    plus_dm_s = _rma(plus_dm, period)
    minus_dm_s = _rma(minus_dm, period)
    with np.errstate(invalid="ignore", divide="ignore"):
        plus_di = 100.0 * plus_dm_s / atr
        minus_di = 100.0 * minus_dm_s / atr
        dx = 100.0 * np.abs(plus_di - minus_di) / (plus_di + minus_di)
    adx = _rma(dx, period)
    return plus_di, minus_di, adx, atr


def ema_full(x, span):
    x = np.asarray(x, float)
    a = 2.0 / (span + 1.0)
    out = np.empty(len(x))
    out[0] = x[0]
    for t in range(1, len(x)):
        out[t] = a * x[t] + (1 - a) * out[t - 1]
    return out


# ---------- fabrique de stratégie (closure liée aux séries pré-calculées) ----------
def make_adm(ohlcv, period=14, adx_min=25.0, atr_mult=2.0,
             use_ema200=True, ema_span=200, reverse=False,
             exit_adx_drop=True, adx_drop_n=3,
             cross_lookback=1, require_rising=True):
    """Construit la fonction strategy_fn(ctx) pour ce ohlcv précis (indices alignés).

    cross_lookback : « croisement RÉCENT » = croisement DI dans les K dernières barres
                     (K=1 = strictement cette barre, lecture littérale ; K>1 laisse à
                     l'ADX le temps de se retourner à la hausse APRÈS le croisement).
    require_rising : exiger ADX[i] > ADX[i-1] (filtre pente de la fiche).
    """
    c = np.asarray(ohlcv["c"], float)
    pDI, mDI, adx, atr = wilder_dmi(ohlcv["h"], ohlcv["l"], c, period)
    ema = ema_full(c, ema_span) if use_ema200 else None

    def _recent_cross(i, bull):
        """Vrai si un croisement (bull/bear) a eu lieu dans les `cross_lookback` barres."""
        for k in range(cross_lookback):
            j = i - k
            if j < 1:
                break
            if bull and pDI[j] > mDI[j] and pDI[j - 1] <= mDI[j - 1]:
                return True
            if (not bull) and mDI[j] > pDI[j] and mDI[j - 1] <= pDI[j - 1]:
                return True
        return False

    def _ready(i):
        if i < 3:
            return False
        vals = (pDI[i], mDI[i], adx[i], adx[i - 1], atr[i])
        if any(not np.isfinite(v) for v in vals):
            return False
        if use_ema200 and not np.isfinite(ema[i]):
            return False
        return True

    def _long_entry(i):
        cross = _recent_cross(i, bull=True) and pDI[i] > mDI[i]
        strong = adx[i] > adx_min
        rising = (adx[i] > adx[i - 1]) if require_rising else True
        trend = (c[i] > ema[i]) if use_ema200 else True
        return cross and strong and rising and trend

    def _short_entry(i):
        cross = _recent_cross(i, bull=False) and mDI[i] > pDI[i]
        strong = adx[i] > adx_min
        rising = (adx[i] > adx[i - 1]) if require_rising else True
        trend = (c[i] < ema[i]) if use_ema200 else True
        return cross and strong and rising and trend

    def _adx_falling(i):
        if not exit_adx_drop or i < adx_drop_n:
            return False
        seq = adx[i - adx_drop_n:i + 1]
        if any(not np.isfinite(v) for v in seq):
            return False
        return all(seq[k] < seq[k - 1] for k in range(1, len(seq)))

    def _sl(i):
        return atr_mult * atr[i] / c[i]

    def adm(ctx):
        i = ctx["i"]
        pos = ctx["position"]
        if not _ready(i):
            return {"signal": 0} if pos == 0 else {"signal": None}

        if pos == 0:
            if _long_entry(i):
                return {"signal": 1, "sl": _sl(i)}
            if _short_entry(i):
                return {"signal": -1, "sl": _sl(i)}
            return {"signal": 0}

        if pos == 1:
            exit_cross = mDI[i] > pDI[i] and mDI[i - 1] <= pDI[i - 1]
            if exit_cross or _adx_falling(i):
                if reverse and _short_entry(i):
                    return {"signal": -1, "sl": _sl(i)}
                return {"signal": 0}
            return {"signal": None}

        # pos == -1
        exit_cross = pDI[i] > mDI[i] and pDI[i - 1] <= mDI[i - 1]
        if exit_cross or _adx_falling(i):
            if reverse and _long_entry(i):
                return {"signal": 1, "sl": _sl(i)}
            return {"signal": 0}
        return {"signal": None}

    return adm
