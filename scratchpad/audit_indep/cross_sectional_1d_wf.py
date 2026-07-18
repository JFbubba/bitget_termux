"""
cross_sectional_1d_wf.py — WALK-FORWARD à L GLISSANT de la piste momentum cross-sectionnel 1D.

Le test précédent CHOISISSAIT L=21 en connaissant tout l'historique (look-ahead de sélection).
Ici : à chaque bloc, on SÉLECTIONNE L sur la fenêtre d'entraînement GLISSANTE précédente
(meilleur Sharpe net maker), on l'applique au bloc OOS SUIVANT, on concatène → track record
OOS honnête, sans look-ahead sur le paramètre. On compare aussi à un L FIXE théorique (14 j,
~2 sem Dobrynskaya = zéro data-mining). Crible de frais. Lecture seule.
"""
import math

import numpy as np

import audit_core as ac
import cross_sectional_1d as cs
from cross_sectional_1d_validate import panel_for_L

CANDS = [7, 10, 14, 21, 30]
K = 5                # jambe plus large (univers élargi ~47 coins)
TRAIN = 365          # fenêtre d'entraînement glissante (jours)
SEL_EVERY = 21       # ré-sélection de L tous les ~mois
FEES_BPS = [6.0, 1.0, 0.0]
FIXED_THEORY = 14    # L fixe a priori (théorie, aucun data-mining)


def net_by_L(data, fee):
    """Série quotidienne net (fee bps/côté) par L candidat, alignée sur l'index de dates commun."""
    out = {}
    for L in CANDS:
        _, fwd, form = panel_for_L(data, L)
        gross, W = cs.portfolio(form, fwd, K)
        out[L] = cs.net_series(gross, W, fee)
    return out


def stats(x):
    x = x[np.isfinite(x)]
    if len(x) < 40:
        return None
    mu, sd = float(np.mean(x)), float(np.std(x))
    t = mu / (sd / math.sqrt(len(x))) if sd > 1e-12 else 0.0
    nw = ac.nw_tstat(x)              # t HAC (Newey-West) sur les blocs OOS concaténés
    return dict(bps=round(mu * 1e4, 2), t=round(t, 2),
               t_nw=round(nw["t_nw"], 2) if nw else float("nan"),
               nw_lag=(nw["lag"] if nw else None),
               sharpe=round(mu / sd * math.sqrt(365), 2) if sd > 1e-12 else 0.0, n=len(x))


def walk_forward(net_sel, net_report):
    """Sélectionne L sur Sharpe trailing (net_sel), applique au bloc OOS suivant en le
    lisant dans net_report (peut être un autre niveau de frais). Retourne l'OOS + choix de L."""
    D = len(next(iter(net_sel.values())))
    oos = np.full(D, np.nan); chosen = []
    d = TRAIN
    while d < D:
        best_L, best_s = None, -1e18
        for L in CANDS:
            w = net_sel[L][d - TRAIN:d]; w = w[np.abs(w) > 0]
            if len(w) < 60:
                continue
            s = w.mean() / (w.std() + 1e-12)
            if s > best_s:
                best_s, best_L = s, L
        end = min(d + SEL_EVERY, D)
        if best_L is not None:
            oos[d:end] = net_report[best_L][d:end]
            chosen.append(best_L)
        d = end
    return oos, chosen


def main():
    data = cs.load_all()
    print(f"WALK-FORWARD à L glissant — {len(data)} cryptos · k={K} · train {TRAIN}j · "
          f"ré-sélection /{SEL_EVERY}j · candidats L={CANDS}\n")
    net_sel = net_by_L(data, 1.0)        # sélection sur le net MAKER (frais de trading visé)
    net_rep = {f: net_by_L(data, f) for f in FEES_BPS}

    print("A) WALK-FORWARD (L choisi OOS sur train glissant) — track record OOS honnête")
    for f in FEES_BPS:
        oos, chosen = walk_forward(net_sel, net_rep[f])
        s = stats(oos)
        tag = "taker" if f == 6 else ("maker" if f == 1 else "brut")
        if s:
            print(f"   frais {int(f)}bps ({tag:<5}) : {s['bps']:+.2f} bps/j · Sharpe {s['sharpe']:+.2f} · "
                  f"t_naif {s['t']:+.2f} · t_NW {s['t_nw']:+.2f} · n {s['n']}")
    _, chosen = walk_forward(net_sel, net_rep[1.0])
    from collections import Counter
    print(f"   L choisis (fréquence) : {dict(Counter(chosen))}")

    print(f"\nB) L FIXE THÉORIQUE = {FIXED_THEORY}j (~2 sem Dobrynskaya, ZÉRO data-mining) — plein échantillon")
    for f in FEES_BPS:
        s = stats(net_rep[f][FIXED_THEORY])
        tag = "taker" if f == 6 else ("maker" if f == 1 else "brut")
        if s:
            print(f"   frais {int(f)}bps ({tag:<5}) : {s['bps']:+.2f} bps/j · Sharpe {s['sharpe']:+.2f} · "
                  f"t_naif {s['t']:+.2f} · t_NW {s['t_nw']:+.2f} · n {s['n']}")
    # sa 2e moitié (OOS temporel du L fixe)
    x = net_rep[1.0][FIXED_THEORY]; D = len(x)
    s2 = stats(x[np.arange(D) >= D // 2])
    if s2:
        print(f"   L={FIXED_THEORY} 2e MOITIÉ (maker) : {s2['bps']:+.2f} bps/j · Sharpe {s2['sharpe']:+.2f} · "
              f"t_naif {s2['t']:+.2f} · t_NW {s2['t_nw']:+.2f}")

    print("\n" + "=" * 78)
    oos, _ = walk_forward(net_sel, net_rep[1.0])
    s = stats(oos)
    if s and s["t_nw"] > 2.0 and s["bps"] > 0:
        print(f"VERDICT : la piste TIENT en walk-forward OOS (t_NW={s['t_nw']} > 2, net maker +{s['bps']} bps/j).")
        print("  Prochaine étape avant tout LIVE : coûts short réalistes (alts illiquides) + biais de survie")
        print("  + univers élargi. Ce serait une NOUVELLE voix ADVISORY (banc gelé §62 intact).")
    elif s:
        print(f"VERDICT : la piste NE tient PAS robustement en walk-forward (t_NW={s['t_nw']}, "
              f"t_naif={s['t']}, net {s['bps']} bps/j).")
        print("  Le momentum cross-sectionnel 1D existe (market-neutral, théorie-cohérent) mais la sélection")
        print("  de L en OOS ne délivre pas un edge significatif stable. Lead à garder VIVANT, pas déployer.")
    print("=" * 78)


if __name__ == "__main__":
    main()
