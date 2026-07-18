"""
funding_features.py — features de FUNDING alignées CAUSALEMENT aux bougies.

Le funding est ORTHOGONAL au prix : funding élevé = longs surchargés -> pression
short contrarian (funding-euphorie, docs/SAVOIR.md). C'est la feature non-prix la
plus documentée et la seule HISTORISÉE chez nous (FUNDING_*.json : BTC/ETH/SOL/XRP/
DOGE, ~3 mois, cadence 8 h). But : compléter le jeu de features du modèle joint
(méthode ERR-014 — « tous les indicateurs ensemble ») avec ce qui MANQUE au prix.

Causalité STRICTE : à la barre t on ne connaît que le funding RÉGLÉ à un ts <= t, et
le z-score n'utilise que les règlements jusqu'à celui-là. Lecture seule, numpy pur.
"""
import json
from pathlib import Path

import numpy as np

DATA = Path("/root/bitget_termux_repo/data_history")


def load_funding(sym):
    """Retourne (ts_ms trié/dédup, taux) ou None si absent."""
    p = DATA / f"FUNDING_{sym}.json"
    if not p.exists():
        return None
    raw = json.loads(p.read_text())
    dd = {int(r[0]): float(r[1]) for r in raw if len(r) >= 2}
    ts = np.array(sorted(dd), dtype=np.int64)
    rate = np.array([dd[int(t)] for t in ts], dtype=float)
    return ts, rate


def _causal_z(rate, zwin):
    """z-score glissant CAUSAL par règlement : z[i] sur la fenêtre [i-zwin+1 .. i]."""
    z = np.full(len(rate), np.nan)
    for i in range(len(rate)):
        w = rate[max(0, i - zwin + 1):i + 1]
        if len(w) >= 8:
            mu, sd = float(w.mean()), float(w.std())
            z[i] = (rate[i] - mu) / sd if sd > 1e-12 else 0.0
    return z


def funding_features(sym, candle_ts, zwin=30):
    """Features funding alignées sur candle_ts (ms), toutes CAUSALES. zwin = nb de
    règlements 8 h pour le z-score. Renvoie {fund_level, fund_z, fund_sign} ; NaN
    quand le symbole n'a pas de funding ou avant le 1er règlement connu."""
    n = len(candle_ts)
    nan = lambda: np.full(n, np.nan)
    out = {"fund_level": nan(), "fund_z": nan(), "fund_sign": nan()}
    f = load_funding(sym)
    if f is None:
        return out
    fts, frate = f
    fz = _causal_z(frate, zwin)
    # dernier règlement <= barre t (forward-fill causal)
    idx = np.searchsorted(fts, np.asarray(candle_ts, dtype=np.int64), side="right") - 1
    ok = idx >= 0
    out["fund_level"][ok] = frate[idx[ok]]
    out["fund_z"][ok] = fz[idx[ok]]
    out["fund_sign"][ok] = np.sign(frate[idx[ok]])
    return out


if __name__ == "__main__":
    import audit_core as ac
    for sym in ("BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "DOGEUSDT", "BNBUSDT"):
        try:
            d = ac.load(sym, "1H")
        except Exception:
            print(f"{sym}: pas de bougies 1H"); continue
        ff = funding_features(sym, d["ts"])
        lvl = ff["fund_level"]; cov = np.mean(np.isfinite(lvl)) * 100
        fin = lvl[np.isfinite(lvl)]
        print(f"{sym:<9} couv={cov:5.1f}%  level[min/méd/max]="
              f"{(fin.min() if len(fin) else float('nan')):+.5f}/"
              f"{(np.median(fin) if len(fin) else float('nan')):+.5f}/"
              f"{(fin.max() if len(fin) else float('nan')):+.5f}  "
              f"z_fin={ff['fund_z'][np.isfinite(ff['fund_z'])][-3:] if np.isfinite(ff['fund_z']).any() else '—'}")
