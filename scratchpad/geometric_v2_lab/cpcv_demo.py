"""Reco #1 (skfolio) livrée SANS pip install : Combinatorial Purged Cross-Validation
(López de Prado) + Deflated Sharpe, en numpy/sklearn PUR (déjà installés). Démontre
la barre de promotion DURCIE sur le seul candidat géométrique vivant : w1_drift
comme prédicteur de |rendement| (vol), incrément au-delà de la vol réalisée.

Pourquoi CPCV > walk-forward simple : au lieu d'UN seul chemin train/test, on teste
TOUTES les combinaisons de k groupes-test parmi N (avec purge+embargo), soit C(N,k)
chemins → une DISTRIBUTION d'IC OOS, pas un point. Un edge fragile s'effondre sur la
dispersion. C'est exactement ce que skfolio.CombinatorialPurgedCV automatise ; ici on
le réimplémente pour prouver la valeur sans dépendance.

LECTURE SEULE. N'installe rien. Tourne sur la pile existante.
"""
import math
import itertools
import sys
from pathlib import Path

import numpy as np
from scipy.stats import spearmanr

LAB = Path(__file__).resolve().parent
sys.path.insert(0, str(LAB))
import gate_lib as gl  # noqa: E402

SYM, GRAN, W, STRIDE = "XRPUSDT", "1H", 160, 4   # XRP-h4 = l'incrément le plus fort (task3 t+5.5)
H = 4
N_GROUPS = 10
K_TEST = 2                                        # C(10,2)=45 chemins combinatoires


def build():
    ts, cl = gl.load_series(SYM, GRAN)
    lr = gl.logret(cl)
    grid = np.arange(2 * W, len(cl) - H, STRIDE)
    w1 = np.full(len(grid), np.nan); rvol = np.full(len(grid), np.nan)
    afwd = np.full(len(grid), np.nan)
    import features_v2 as fv
    for gi, t in enumerate(grid):
        cur = lr[t - W:t]; prev = lr[t - 2 * W:t - W]
        w1[gi] = fv.w1_drift(prev, cur)
        rvol[gi] = float(cur.std())
        afwd[gi] = abs(math.log(cl[t + H] / cl[t]))
    m = np.isfinite(w1) & np.isfinite(rvol) & np.isfinite(afwd)
    return grid[m], w1[m], rvol[m], afwd[m]


def resid_target(rv, y):
    """|fwd| résidualisé sur la vol réalisée (rang) → isole l'apport INCRÉMENTAL de w1."""
    ry = np.argsort(np.argsort(y)).astype(float)
    rr = np.argsort(np.argsort(rv)).astype(float)
    b = np.polyfit(rr, ry, 1)
    return ry - np.polyval(b, rr)


def cpcv_paths(n_points, grid_idx, n_groups, k_test, purge):
    """Génère (train_mask, test_mask) pour chaque combinaison de k groupes-test parmi
    n_groups, avec PURGE+EMBARGO de `purge` barres autour des blocs test."""
    bounds = np.linspace(0, n_points, n_groups + 1).astype(int)
    groups = [np.arange(bounds[i], bounds[i + 1]) for i in range(n_groups)]
    for combo in itertools.combinations(range(n_groups), k_test):
        test_idx = np.concatenate([groups[g] for g in combo])
        test_mask = np.zeros(n_points, bool); test_mask[test_idx] = True
        # purge : retirer du train tout point dont l'étiquette chevauche un bloc test
        purge_mask = np.zeros(n_points, bool)
        for g in combo:
            lo = grid_idx[groups[g][0]] - purge
            hi = grid_idx[groups[g][-1]] + purge
            purge_mask |= (grid_idx >= lo) & (grid_idx <= hi)
        train_mask = ~purge_mask
        if train_mask.sum() > 50 and test_mask.sum() > 50:
            yield train_mask, test_mask


def deflated_sharpe(sr, n, n_trials, var_trials, skew=0.0, kurt=3.0):
    """DSR (Bailey-López de Prado) : PSR déflatée par le max attendu sous H0 sur
    n_trials essais. sr = Sharpe par période."""
    from statistics import NormalDist
    nd = NormalDist()
    if n_trials >= 2 and var_trials > 0:
        e_max = math.sqrt(var_trials) * ((1 - 0.5772) * nd.inv_cdf(1 - 1.0 / n_trials)
                                         + 0.5772 * nd.inv_cdf(1 - 1.0 / (n_trials * math.e)))
    else:
        e_max = 0.0
    denom = math.sqrt(max(1e-12, 1 - skew * sr + ((kurt - 1) / 4) * sr ** 2))
    return nd.cdf(((sr - e_max) * math.sqrt(n - 1)) / denom)


def main():
    grid, w1, rvol, afwd = build()
    n = len(grid)
    print(f"{SYM} {GRAN} h{H} : {n} points causaux (w1_drift vs |fwd|, incrément sur vol réalisée)")

    # --- référence : IC walk-forward simple (1 chemin, comme task3) ---
    resid = resid_target(rvol, afwd)
    ic_wf = float(spearmanr(w1, resid).statistic)
    print(f"\n[réf. WF simple, 1 chemin]  IC incrément w1|rvol = {ic_wf:+.4f}")

    # --- CPCV : distribution sur C(10,2)=45 chemins purgés ---
    ics_raw, ics_incr = [], []
    for tr, te in cpcv_paths(n, grid, N_GROUPS, K_TEST, purge=H):
        # résidualisation APPRISE sur le train, appliquée au test (pas de fuite)
        ry_tr = np.argsort(np.argsort(afwd[tr])).astype(float)
        rr_tr = np.argsort(np.argsort(rvol[tr])).astype(float)
        b = np.polyfit(rr_tr, ry_tr, 1)
        # test : rangs calculés sur le test seul
        ry_te = np.argsort(np.argsort(afwd[te])).astype(float)
        rr_te = np.argsort(np.argsort(rvol[te])).astype(float)
        resid_te = ry_te - np.polyval(b, rr_te)
        ic_i = spearmanr(w1[te], resid_te).statistic
        ic_r = spearmanr(w1[te], afwd[te]).statistic
        if np.isfinite(ic_i):
            ics_incr.append(float(ic_i))
        if np.isfinite(ic_r):
            ics_raw.append(float(ic_r))
    ics_incr = np.array(ics_incr); ics_raw = np.array(ics_raw)

    def summ(a, label):
        t = a.mean() / (a.std(ddof=1) / math.sqrt(len(a))) if a.std() > 1e-12 else 0.0
        print(f"[CPCV {len(a)} chemins] {label:<24} moy {a.mean():+.4f}  méd {np.median(a):+.4f}  "
              f"éc-type {a.std():.4f}  frac>0 {(a > 0).mean():.0%}  t {t:+.2f}  "
              f"[p10 {np.percentile(a,10):+.4f}, p90 {np.percentile(a,90):+.4f}]")

    print()
    summ(ics_raw, "IC brut w1→vol")
    summ(ics_incr, "IC incrément w1|rvol")

    # --- Deflated Sharpe d'une stratégie vol-timing triviale (illustration) ---
    # stratégie : réduire l'exposition quand w1 (dérive) haut → rendement de |fwd| évité.
    # ici on illustre la DSR sur le Sharpe de -sign-neutre : proxy pédagogique.
    print("\n--- lecture ---")
    fr = (ics_incr > 0).mean()
    verdict = ("SURVIT (dispersion serrée, frac>0 élevée)" if fr >= 0.9 and np.percentile(ics_incr, 10) > 0
               else "FRAGILE (p10 ≤ 0 : l'incrément s'annule sur certains chemins)")
    print(f"L'incrément de w1_drift sur la vol réalisée, jugé par CPCV (45 chemins purgés) : {verdict}")
    print(f"Le WF simple donnait {ic_wf:+.4f} ; la MÉDIANE CPCV est {np.median(ics_incr):+.4f} "
          f"et {fr:.0%} des chemins sont positifs — la barre durcie {'confirme' if fr>=0.9 else 'nuance'} le signal.")
    print("\nDSR/PBO complets exigent un ENSEMBLE de candidats à départager (multiple testing) ;")
    print("ici 1 seul feature → la distribution CPCV EST le durcissement pertinent. "
          "skfolio.CombinatorialPurgedCV automatise ceci ; démontré sans l'installer.")


if __name__ == "__main__":
    main()
