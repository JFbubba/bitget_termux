"""Re-mesure walk-forward de la cible RIDGE (§78) sur le journal ACTUEL. LECTURE SEULE.

Question (alerte §96 du 08/07) : la cible ridge — qui donne à carry/simons un
coefficient positif malgré un pearson marginal négatif (effet suppresseur) —
bat-elle ENCORE les poids courants hors-échantillon ? La mesure d'origine
(« IC consensus +0.123 vs +0.076, meilleur sur chaque pli ») date d'avant.

Protocole (réplique §78, honnête) :
  - données : brain_log_history.jsonl via live_ic_audit.charger_entrees (queue, ERR-006) ;
  - échantillon : vote des 14 agents -> rendement log forward à l'horizon H
    (premier point >= ts+H, tolérance 600 s — identique à _ridge_mults) ;
  - 6 plis temporels contigus ; pli 0 = amorçage seul ; plis 1..5 testés,
    entraînement = tout AVANT le pli avec PURGE ts < début_pli − (H+600)
    (le rendement forward du train est réalisé avant le test — pas de fuite) ;
  - cible ridge réapprise à CHAQUE pli via swarm_brain._ridge_solve (le code de
    production : clip négatifs, normalisation, bornes [0.25, 2.5], λ=0.2) ;
  - comparaison : ridge_wf vs poids COURANTS (sb.load_weights()) vs ÉGAUX (1.0).
    ⚠ biais assumé EN FAVEUR des poids courants : ils dérivent de la cible ridge
    calculée sur TOUT le journal (test inclus). Si ridge_wf les bat quand même,
    la conclusion est forte ; l'inverse est ininterprétable sans ce caveat.
  - horizons : 900 / 3600 / 14400 s (les 3 instrumentés par live_ic_audit ;
    production = 3600). # tf-ladder-ok : journal profond de ~5 j — D1/W1 n'ont
    pas de rendements forward mesurables ; on couvre TOUS les horizons faisables.
  - métriques : IC pearson (métrique de sizing §96) ET IC de rang, par pli.

Sortie : tableau par horizon/pli + coefficient carry par pli (stabilité du
suppresseur). Aucun poids modifié, aucun ordre.
"""

import math
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import live_ic_audit as lia          # noqa: E402
import swarm_brain as sb             # noqa: E402

HORIZONS_S = (900, 3600, 14400)
TOL_S = 600
N_PLIS = 6


def echantillons(entrees, horizon_s):
    """[(ts, x[14], y)] — rendement log forward à horizon (tolérance TOL_S), par symbole."""
    par_sym = {}
    for e in entrees:
        par_sym.setdefault(e["symbol"], []).append(e)
    out = []
    for s, seq in par_sym.items():
        seq.sort(key=lambda x: x.get("ts", 0))
        j = 0
        for i, e in enumerate(seq):
            cible_ts = e["ts"] + horizon_s
            j = max(j, i + 1)
            while j < len(seq) and seq[j]["ts"] < cible_ts:
                j += 1
            if j >= len(seq) or seq[j]["ts"] - cible_ts > TOL_S:
                continue
            x = [float(e["votes"].get(a, 0) or 0) for a in sb.AGENTS]
            out.append((e["ts"], x, math.log(seq[j]["price"] / e["price"])))
    out.sort(key=lambda t: t[0])
    return out


def ic_pair(scores, rets):
    """(pearson, rang) — None si dégénéré."""
    s = np.asarray(scores, dtype=float)
    r = np.asarray(rets, dtype=float)
    if len(s) < 30 or s.std() < 1e-12 or r.std() < 1e-12:
        return None, None
    pearson = float(np.corrcoef(s, r)[0, 1])
    rs = np.argsort(np.argsort(s)).astype(float)
    rr = np.argsort(np.argsort(r)).astype(float)
    rang = float(np.corrcoef(rs, rr)[0, 1])
    return pearson, rang


def consensus(X, w):
    return [sum(wi * xi for wi, xi in zip(w, x)) for x in X]


def main():
    entrees = lia.charger_entrees()
    poids_courants = sb.load_weights()
    w_cour = [float(poids_courants.get(a, 1.0)) for a in sb.AGENTS]
    w_egaux = [1.0] * len(sb.AGENTS)
    i_carry = sb.AGENTS.index("carry")
    i_simons = sb.AGENTS.index("simons")

    print(f"journal : {len(entrees)} entrées · agents {len(sb.AGENTS)} · λ=0.2 · plis {N_PLIS}")
    for H in HORIZONS_S:
        ech = echantillons(entrees, H)
        if len(ech) < 2000:
            print(f"\n— horizon {H} s : {len(ech)} échantillons (<2000) — IGNORÉ")
            continue
        ts_all = [t for t, _, _ in ech]
        t0, t1 = ts_all[0], ts_all[-1]
        bornes = [t0 + (t1 - t0) * k / N_PLIS for k in range(N_PLIS + 1)]
        print(f"\n— horizon {H} s : {len(ech)} échantillons —")
        print(f"{'pli':>4}{'n_train':>9}{'n_test':>8}{'ridge_p':>9}{'cour_p':>8}"
              f"{'egal_p':>8}{'ridge_rg':>10}{'cour_rg':>9}{'m_carry':>9}{'m_simons':>10}")
        cumul = {"ridge_p": [], "cour_p": [], "egal_p": [], "ridge_rg": [], "cour_rg": []}
        for k in range(1, N_PLIS):
            debut, fin = bornes[k], bornes[k + 1]
            purge = debut - (H + TOL_S)
            train = [(x, y) for t, x, y in ech if t < purge]
            test = [(x, y) for t, x, y in ech if debut <= t < fin]
            if len(train) < 500 or len(test) < 200:
                print(f"{k:>4}  (train {len(train)} / test {len(test)} insuffisants)")
                continue
            Xtr = [x for x, _ in train]
            Ytr = [y for _, y in train]
            mults = sb._ridge_solve(Xtr, Ytr, 0.2)
            if not mults:
                print(f"{k:>4}  (ridge dégénéré)")
                continue
            Xte = [x for x, _ in test]
            Yte = [y for _, y in test]
            r_p, r_rg = ic_pair(consensus(Xte, mults), Yte)
            c_p, c_rg = ic_pair(consensus(Xte, w_cour), Yte)
            e_p, _ = ic_pair(consensus(Xte, w_egaux), Yte)
            if r_p is None or c_p is None:
                print(f"{k:>4}  (IC dégénéré)")
                continue
            cumul["ridge_p"].append(r_p); cumul["cour_p"].append(c_p)
            cumul["egal_p"].append(e_p); cumul["ridge_rg"].append(r_rg)
            cumul["cour_rg"].append(c_rg)
            print(f"{k:>4}{len(train):>9}{len(test):>8}{r_p:>+9.3f}{c_p:>+8.3f}"
                  f"{e_p:>+8.3f}{r_rg:>+10.3f}{c_rg:>+9.3f}"
                  f"{mults[i_carry]:>9.2f}{mults[i_simons]:>10.2f}")
        if cumul["ridge_p"]:
            m = {k2: sum(v) / len(v) for k2, v in cumul.items()}
            gagne = sum(1 for a, b in zip(cumul["ridge_p"], cumul["cour_p"]) if a > b)
            print(f"{'moy':>4}{'':>9}{'':>8}{m['ridge_p']:>+9.3f}{m['cour_p']:>+8.3f}"
                  f"{m['egal_p']:>+8.3f}{m['ridge_rg']:>+10.3f}{m['cour_rg']:>+9.3f}"
                  f"   ridge>courants : {gagne}/{len(cumul['ridge_p'])} plis (pearson)")
    print("\nLecture seule. Aucun poids modifié. Aucun ordre.")


if __name__ == "__main__":
    main()
