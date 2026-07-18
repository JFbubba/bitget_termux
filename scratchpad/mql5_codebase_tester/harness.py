"""Banc de test de SIGNAL réutilisable — le cœur de l'agent testeur de code base.
LECTURE SEULE : lit data_history/ (bougies réelles Bitget), aucun ordre.

Un item de la code base mql5 (indicateur/EA) est d'abord RÉIMPLÉMENTÉ EN PYTHON
(sa logique, jamais son code MQL5 exécuté — ligne rouge) sous la forme d'une
fonction de signal causale, puis passé à test_signal() qui mesure son edge
directionnel NET DE FRAIS sur l'échelle TF complète (ERR-001), plis NON
chevauchants purgés (t-stats non gonflés), porte alignée bot (§77 : t>=3).

Contrat du signal :
    signal_fn(window) -> float dans [-1, 1]
    window = dict d'arrays numpy causaux : {'o','h','l','c','v'} des W dernières barres
             (la DERNIÈRE = barre courante ; le futur n'est JAMAIS passé).
    +1 = long fort, -1 = short fort, 0 = neutre.
"""
from __future__ import annotations
import math
from pathlib import Path
import numpy as np
from scipy.stats import spearmanr

import sys
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
import candles_history as ch  # noqa: E402

TFS = ["1m", "5m", "15m", "30m", "1H", "4H", "1D", "1W"]   # échelle complète ERR-001
FEES = {"0bps": 0.0, "maker_4bps": 0.0004, "taker_12bps": 0.0012}   # round-trip
T_GATE = 3.0                                                        # §77
N_ORIGINS = 300           # origines NON chevauchantes visées par (sym,tf)
WARMUP = 160              # barres de contexte min avant la 1re évaluation


# ---- méthodo purgée (copie fidèle de gate_lib du labo geometric) --------------
def purged_folds(idx, h, n_folds=6):
    idx = np.asarray(idx)
    lo, hi = idx.min(), idx.max()
    bounds = [lo + (hi - lo) * k / n_folds for k in range(n_folds + 1)]
    out = []
    for k in range(n_folds):
        s = (idx >= bounds[k] + h) & (idx < bounds[k + 1])
        keep, last = [], -10 ** 9
        for j in np.where(s)[0]:
            if idx[j] >= last + h:
                keep.append(j); last = idx[j]
        out.append(np.array(keep, dtype=int))
    return out


def t_across_folds(vals):
    v = np.asarray([x for x in vals if np.isfinite(x)], dtype=float)
    if len(v) < 3:
        return 0.0, 0.0, len(v)
    se = v.std(ddof=1) / math.sqrt(len(v))
    return float(v.mean()), (float(v.mean() / se) if se > 1e-12 else 0.0), len(v)


def ic_rank(x, y):
    x = np.asarray(x, float); y = np.asarray(y, float)
    if len(x) < 8 or x.std() < 1e-12 or y.std() < 1e-12:
        return np.nan
    return float(spearmanr(x, y).statistic)


def _load_ohlcv(sym, tf, cap=15000):
    rows = ch.load(sym, tf)
    if not rows:
        return None
    rows = sorted(rows, key=lambda r: r[0])[-cap:]
    a = np.array(rows, dtype=float)   # cols: ts,o,h,l,c,v
    return {"o": a[:, 1], "h": a[:, 2], "l": a[:, 3], "c": a[:, 4], "v": a[:, 5]}


def _eval_one(signal_fn, sym, tf, h=1, w=WARMUP):
    d = _load_ohlcv(sym, tf)
    if d is None:
        return None
    n = len(d["c"])
    if n < w + h + 60:
        return {"sym": sym, "tf": tf, "insufficient": True, "n": n}
    logp = np.log(np.clip(d["c"], 1e-12, None))
    grid = np.arange(w, n - h)
    stride = max(h, len(grid) // N_ORIGINS)
    origins = grid[::stride]
    votes, rets, idx = [], [], []
    for t in origins:
        win = {k: d[k][t - w:t + 1] for k in d}     # causal : inclut t, exclut le futur
        try:
            v = float(signal_fn(win))
        except Exception:
            v = 0.0
        if not math.isfinite(v):
            v = 0.0
        votes.append(max(-1.0, min(1.0, v)))
        rets.append(float(logp[t + h] - logp[t]))
        idx.append(int(t))
    return _score(np.array(idx), np.array(votes), np.array(rets), h, sym, tf)


def _score(idx, votes, rets, h, sym, tf):
    if len(rets) < 30 or np.std(votes) < 1e-9:
        return {"sym": sym, "tf": tf, "n": len(rets), "degenerate": True}
    folds = [f for f in purged_folds(idx, h, 6) if len(f) >= 8]
    ic = ic_rank(votes, rets)
    _, ic_t, _ = t_across_folds([ic_rank(votes[f], rets[f]) for f in folds])
    hit = float(np.mean((np.sign(votes) == np.sign(rets))[np.sign(votes) != 0])) if np.any(np.sign(votes) != 0) else float("nan")
    out = {"sym": sym, "tf": tf, "n": len(rets), "ic": _r(ic), "ic_t": _r(ic_t),
           "hit": _r(hit), "pnl": {}}
    for name, fee in FEES.items():
        pnl = np.sign(votes) * rets - fee * (np.abs(np.sign(votes)))   # frais seulement si on trade
        _, t, _ = t_across_folds([float(pnl[f].mean()) for f in folds])
        out["pnl"][name] = {"bps": _r(float(pnl.mean()) * 1e4), "t": _r(t)}
    tk = out["pnl"]["taker_12bps"]
    out["passe"] = bool(tk["bps"] is not None and tk["bps"] > 0 and tk["t"] is not None and tk["t"] >= T_GATE)
    return out


def _r(x):
    try:
        return round(float(x), 4) if math.isfinite(float(x)) else None
    except Exception:
        return None


def test_signal(signal_fn, name, symbols, tfs=None, h=1):
    """Teste un signal sur l'échelle TF complète × symboles. Renvoie un rapport."""
    tfs = tfs or TFS
    res = {"name": name, "h": h, "configs": [], "n_pass": 0}
    for sym in symbols:
        for tf in tfs:
            r = _eval_one(signal_fn, sym, tf, h)
            if r is None:
                continue
            res["configs"].append(r)
            if r.get("passe"):
                res["n_pass"] += 1
    return res


def print_report(res):
    print(f"=== TEST SIGNAL : {res['name']} (h={res['h']}) ===")
    print(f"{'sym':<9} {'tf':<4} {'IC':>7} {'IC_t':>6} {'hit':>5} "
          f"{'net12bps':>9} {'t':>6}  porte")
    for c in res["configs"]:
        if c.get("insufficient") or c.get("degenerate"):
            print(f"{c['sym']:<9} {c['tf']:<4}  (n={c.get('n','?')} "
                  f"{'insuff' if c.get('insufficient') else 'dégénéré'})")
            continue
        tk = c["pnl"]["taker_12bps"]
        flag = "✅" if c["passe"] else ""
        print(f"{c['sym']:<9} {c['tf']:<4} {str(c['ic']):>7} {str(c['ic_t']):>6} "
              f"{str(c['hit']):>5} {str(tk['bps']):>9} {str(tk['t']):>6}  {flag}")
    print(f"\n-> {res['n_pass']}/{len(res['configs'])} configs passent la porte "
          f"(net taker>0 ET t>=3).")
