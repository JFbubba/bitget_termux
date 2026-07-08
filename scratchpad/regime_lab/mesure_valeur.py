"""
mesure_valeur.py — le flag de régime a-t-il de la valeur MESURABLE ? (labo §102)

Protocole (honnête, lecture seule) :
  - Données : candles_history.load (data_history/), échelle COMPLÈTE disponible
    M5·M15·M30·H1·H4·D1 + W1 par ré-échantillonnage du 1D (ERR-001), profondeur
    réelle ANNOTÉE par TF. Symboles : BTCUSDT, ETHUSDT.
  - Flags CAUSAUX (regime_flags.py) : HMM 2/3 états (fit TRAIN seul + filtrage
    forward manuel — jamais predict/Viterbi), ruptures Pelt-rbf sur fenêtre
    glissante (rupture récente, âge du régime), baseline vol-EWMA>médiane
    glissante, baseline flag ALÉATOIRE à même taux de bascule (chaîne de Markov
    appariée, 100 graines).
  - Walk-forward PURGÉ : échantillons NON CHEVAUCHANTS (pas = horizon, comme
    agent_validation.purged_forward_returns) ; 7 blocs temporels contigus,
    bloc 0 = amorçage, blocs 1..6 testés ; train = tout AVANT le pli avec
    purge t + h < début_pli (le label du train est réalisé avant le test).
  - Valeur mesurée PAR PLI :
      a) pertinence : le flag prédit-il |rendement forward| ? (IC de rang de
         P(état haute-vol) et de la vol EWMA vs |fwd| — le HMM ajoute-t-il
         quelque chose à la vol EWMA ?)
      b) edge conditionnel : IC (rang ET pearson) du momentum multi-périodes
         vs rendement forward DANS chaque régime vs GLOBAL ; séparation
         delta = IC(régime 1) − IC(régime 0), t-stat sur les plis, z vs nul
         aléatoire apparié.
      c) robustesse : cohérence des flags entre BTC/ETH et entre TF.
  - Graines fixées (SEED=42, nul 1234..). Sortie : resultats.json (incrémental).

Aucun ordre, aucune écriture hors scratchpad/regime_lab/. VERDICT: SAFE.
"""

import json
import sys
import time
from pathlib import Path

import numpy as np

ICI = Path(__file__).resolve().parent
sys.path.insert(0, str(ICI))
sys.path.insert(0, str(ICI.parent.parent))          # racine du dépôt (lecture seule)

import candles_history as ch                         # noqa: E402
import regime_flags as rf                            # noqa: E402

SYMBOLES = ("BTCUSDT", "ETHUSDT")
N_BLOCS = 7                                          # bloc 0 = amorçage, 1..6 testés
N_SEEDS_NUL = 100
SORTIE = ICI / "resultats.json"

TF_CFG = {
    # h = horizon forward (barres), step = pas d'échantillonnage (step=h : labels
    # NON chevauchants ; step<h en D1/W1 faute de profondeur — chevauchement
    # ANNOTÉ, les t-stats restent au niveau des plis), window = fenêtre ruptures,
    # trail = médiane vol, lookbacks = momentum, min_side = n min par régime
    "5m":  dict(h=12, step=12, window=240, trail=500, lookbacks=(4, 8, 16, 32, 64),
                min_size=8, jump=2, min_side=20),
    "15m": dict(h=16, step=16, window=240, trail=500, lookbacks=(4, 8, 16, 32, 64),
                min_size=8, jump=2, min_side=20),
    "30m": dict(h=16, step=16, window=240, trail=500, lookbacks=(4, 8, 16, 32, 64),
                min_size=8, jump=2, min_side=20),
    "1H":  dict(h=24, step=24, window=240, trail=500, lookbacks=(4, 8, 16, 32, 64),
                min_size=8, jump=2, min_side=20),
    "4H":  dict(h=6,  step=6,  window=240, trail=500, lookbacks=(4, 8, 16, 32, 64),
                min_size=8, jump=2, min_side=20),
    "1D":  dict(h=5,  step=1,  window=120, trail=250, lookbacks=(2, 4, 8, 16, 32),
                min_size=6, jump=1, min_side=15),
    "1W":  dict(h=4,  step=1,  window=40,  trail=52,  lookbacks=(2, 4, 8, 13, 26),
                min_size=4, jump=1, min_side=8),
}
TF_S = {"5m": 300, "15m": 900, "30m": 1800, "1H": 3600, "4H": 14400,
        "1D": 86400, "1W": 604800}


# ------------------------------------------------------------------ données

def charge_serie(sym, tf):
    """(ts_s, close) triés. 1W = ré-échantillonnage ISO-semaine du 1D."""
    if tf == "1W":
        rows = ch.load(sym, "1D")
        if not rows:
            return None, None
        import datetime
        utc = datetime.timezone.utc
        sem = {}
        for r in rows:                               # dernier close de chaque semaine ISO
            d = datetime.datetime.fromtimestamp(r[0] / 1000, utc)
            k = d.isocalendar()[:2]
            sem[k] = (r[0] / 1000.0, float(r[4]))
        vals = sorted(sem.values())
        return np.array([v[0] for v in vals]), np.array([v[1] for v in vals])
    rows = ch.load(sym, tf)
    if not rows:
        return None, None
    return (np.array([r[0] / 1000.0 for r in rows]),
            np.array([float(r[4]) for r in rows]))


# ------------------------------------------------------------------ mesure

def ic_cond(mom, fwd, flag, min_side):
    """IC conditionnel par régime + global. None si un côté est trop petit."""
    g_p, g_rg = rf.ic_pair(mom, fwd, min_n=min_side)
    m0, m1 = (flag == 0), (flag == 1)
    if m0.sum() < min_side or m1.sum() < min_side:
        return None
    p0, rg0 = rf.ic_pair(mom[m0], fwd[m0], min_n=min_side)
    p1, rg1 = rf.ic_pair(mom[m1], fwd[m1], min_n=min_side)
    if None in (p0, p1, rg0, rg1, g_p, g_rg):
        return None
    return {"n0": int(m0.sum()), "n1": int(m1.sum()),
            "ic0_rang": rg0, "ic1_rang": rg1, "delta_rang": rg1 - rg0,
            "ic0_p": p0, "ic1_p": p1, "delta_p": p1 - p0,
            "ic_global_rang": g_rg, "ic_global_p": g_p}


def stats_plis(valeurs):
    """(moyenne, écart-type, t) sur les plis valides."""
    v = [x for x in valeurs if x is not None and np.isfinite(x)]
    if len(v) < 2:
        return (float(np.mean(v)) if v else None), None, None, len(v)
    m, sd = float(np.mean(v)), float(np.std(v, ddof=1))
    t = m / (sd / np.sqrt(len(v))) if sd > 1e-12 else None
    return m, sd, t, len(v)


def traite_serie(sym, tf):
    cfg = TF_CFG[tf]
    ts, close = charge_serie(sym, tf)
    if ts is None or len(ts) < 200:
        return {"statut": "TROP PEU PROFOND", "n_bars": 0 if ts is None else len(ts)}
    h, window, trail = cfg["h"], cfg["window"], cfg["trail"]
    logp = rf.log_prices(close)
    r = rf.log_returns(logp)
    vol = rf.ewma_vol(r)
    mom_all = rf.momentum_signal(logp, vol, cfg["lookbacks"])
    n = len(logp)
    warmup = max(window, trail, max(cfg["lookbacks"])) + 1
    idx = np.arange(warmup, n - h, cfg["step"])      # pas = step (voir TF_CFG)
    if len(idx) < 14 * (N_BLOCS - 1):
        return {"statut": "TROP PEU PROFOND",
                "n_bars": int(n), "n_echantillons": int(len(idx)),
                "profondeur_jours": round((ts[-1] - ts[0]) / 86400, 1)}
    fwd = logp[idx + h] - logp[idx]
    mom = mom_all[idx]
    obs = r * 100.0

    # --- ruptures : pen calibré sur le bloc d'AMORÇAGE, âges à tous les points
    blocs = np.array_split(np.arange(len(idx)), N_BLOCS)
    calib = idx[blocs[0]][::max(1, len(blocs[0]) // 20)][:20]
    pen, dwell = rf.calibre_pen(obs, calib, window, cfg["min_size"], cfg["jump"])
    t0 = time.time()
    ages = rf.ruptures_ages(obs, idx, window, pen, cfg["min_size"], cfg["jump"])
    t_rupt = time.time() - t0
    volflag_all = rf.flag_vol_ewma(vol, idx, trail)

    noms_flags = ("hmm2", "hmm3", "rupt_recent", "rupt_age", "vol_ewma")
    par_pli = {f: [] for f in noms_flags}
    pertinence = {"ic_phaut_absfwd": [], "ic_vol_absfwd": [], "exces_ratio_absfwd_hmm2": []}
    nul_par_seed = [[] for _ in range(N_SEEDS_NUL)]  # delta_rang nul, par pli
    flags_ts = {}                                    # ts -> flag hmm2 (cohérence)
    plis_detail = []

    for k in range(1, N_BLOCS):
        pos_te = blocs[k]
        if len(pos_te) == 0:
            continue
        debut_bar = idx[pos_te[0]]
        pos_tr = np.where(idx + h < debut_bar)[0]    # PURGE : label réalisé avant test
        if len(pos_tr) < 50:
            plis_detail.append({"pli": k, "statut": "train insuffisant"})
            continue
        fin_bar_tr = int(idx[pos_tr[-1]] + h)        # dernière obs utilisable au train
        b_fit0 = max(1, fin_bar_tr - 20000)          # cap coût HMM
        te_bars = idx[pos_te]
        fin_bar_te = int(te_bars[-1])

        # --- HMM fit TRAIN seul, filtrage forward causal jusqu'au test
        m2 = rf.hmm_fit(obs[b_fit0:fin_bar_tr + 1], 2, seed=rf.SEED)
        m3 = rf.hmm_fit(obs[b_fit0:fin_bar_tr + 1], 3, seed=rf.SEED)
        b_flt0 = max(1, fin_bar_tr - 20000)          # long run-in avant le test
        d = {"pli": k, "n_test": int(len(pos_te))}
        fl = {}
        if m2 is not None:
            a2 = rf.forward_filter(obs[b_flt0:fin_bar_te + 1], m2)
            p2 = a2[te_bars - b_flt0, 1]             # P(état haute-vol | obs<=t)
            fl["hmm2"] = (p2 > 0.5).astype(int)
        if m3 is not None:
            a3 = rf.forward_filter(obs[b_flt0:fin_bar_te + 1], m3)
            fl["hmm3"] = (np.argmax(a3[te_bars - b_flt0], axis=1) == 2).astype(int)
        ages_tr, ages_te = ages[pos_tr], ages[pos_te]
        seuil_recent = max(h, window // 10)
        fl["rupt_recent"] = (ages_te <= seuil_recent).astype(int)
        fl["rupt_age"] = (ages_te > np.median(ages_tr)).astype(int)
        fl["vol_ewma"] = volflag_all[pos_te]

        fwd_te, mom_te = fwd[pos_te], mom[pos_te]
        abs_fwd = np.abs(fwd_te)

        # a) pertinence vol
        if m2 is not None:
            pertinence["ic_phaut_absfwd"].append(rf.rank_ic(p2, abs_fwd))
            f2 = fl["hmm2"]
            if f2.min() != f2.max():
                mu0 = float(abs_fwd[f2 == 0].mean())
                mu1 = float(abs_fwd[f2 == 1].mean())
                # EXCÈS de ratio (ratio − 1) : le t se lit contre le nul ratio=1
                pertinence["exces_ratio_absfwd_hmm2"].append(
                    mu1 / mu0 - 1.0 if mu0 > 0 else None)
            else:
                pertinence["exces_ratio_absfwd_hmm2"].append(None)
        else:
            pertinence["ic_phaut_absfwd"].append(None)
            pertinence["exces_ratio_absfwd_hmm2"].append(None)
        pertinence["ic_vol_absfwd"].append(rf.rank_ic(vol[te_bars], abs_fwd))

        # b) edge conditionnel par flag
        for f in noms_flags:
            res = ic_cond(mom_te, fwd_te, fl[f], cfg["min_side"]) if f in fl else None
            par_pli[f].append(res)
            d[f] = res

        # nul aléatoire apparié au hmm2
        if "hmm2" in fl and fl["hmm2"].min() != fl["hmm2"].max():
            nuls = rf.markov_null_flags(fl["hmm2"], N_SEEDS_NUL)
            if nuls is not None:
                for s in range(N_SEEDS_NUL):
                    rn = ic_cond(mom_te, fwd_te, nuls[s], cfg["min_side"])
                    nul_par_seed[s].append(rn["delta_rang"] if rn else None)

        if "hmm2" in fl:
            for j, p in enumerate(pos_te):
                flags_ts[float(ts[idx[p]])] = int(fl["hmm2"][j])
        plis_detail.append(d)

    # --- agrégats
    flags_out = {}
    for f in noms_flags:
        res_valides = [x for x in par_pli[f] if x]
        ag = {"n_plis_valides": len(res_valides)}
        for cle in ("delta_rang", "delta_p", "ic_global_rang", "ic_global_p",
                    "ic0_rang", "ic1_rang"):
            m, sd, t, nf = stats_plis([x[cle] for x in res_valides])
            ag[cle] = {"moy": m, "sd": sd, "t": t}
        flags_out[f] = ag
    # z du hmm2 vs nul apparié (delta_rang moyen sur plis, par graine)
    obs_deltas = [x["delta_rang"] for x in par_pli["hmm2"] if x]
    z_nul = p_emp = None
    if obs_deltas and any(any(v is not None for v in s) for s in nul_par_seed):
        obs_moy = float(np.mean(obs_deltas))
        moys_nul = []
        for s in nul_par_seed:
            v = [x for x in s if x is not None]
            if v:
                moys_nul.append(float(np.mean(v)))
        if len(moys_nul) >= 30:
            mn, sn = float(np.mean(moys_nul)), float(np.std(moys_nul, ddof=1))
            z_nul = (obs_moy - mn) / sn if sn > 1e-12 else None
            p_emp = float((1 + sum(1 for x in moys_nul if abs(x) >= abs(obs_moy)))
                          / (len(moys_nul) + 1))
    flags_out["hmm2"]["z_vs_aleatoire"] = z_nul
    flags_out["hmm2"]["p_empirique"] = p_emp

    pert_out = {}
    for cle, vals in pertinence.items():
        m, sd, t, nf = stats_plis(vals)
        pert_out[cle] = {"moy": m, "sd": sd, "t": t, "n_plis": nf}

    return {
        "statut": "OK",
        "profondeur_jours": round((ts[-1] - ts[0]) / 86400, 1),
        "n_bars": int(n), "n_echantillons": int(len(idx)),
        "horizon_barres": h, "pas_echantillonnage": cfg["step"],
        "chevauchement_labels": round(h / cfg["step"], 1), "pen_ruptures": pen,
        "duree_seg_calibree": None if dwell is None else round(dwell, 1),
        "t_ruptures_s": round(t_rupt, 1),
        "pertinence_vol": pert_out,
        "flags": flags_out,
        "plis": plis_detail,
        "_flags_ts": flags_ts,                       # retiré avant écriture JSON
    }


# ------------------------------------------------------------------ cohérence

def coherence(resultats):
    """phi (corrélation de flags binaires hmm2) BTC vs ETH par TF, et entre TF
    (chaque TF fin vs 1H) par symbole, sur les timestamps appariés."""
    out = {"btc_vs_eth": {}, "inter_tf_vs_1H": {}}

    def phi(d1, d2, tol_s):
        cles = []
        ts2 = sorted(d2.keys())
        if not ts2 or not d1:
            return None, 0
        import bisect
        for t1 in d1:
            i = bisect.bisect_right(ts2, t1) - 1
            if i >= 0 and t1 - ts2[i] <= tol_s:
                cles.append((d1[t1], d2[ts2[i]]))
        if len(cles) < 30:
            return None, len(cles)
        a = np.array([c[0] for c in cles], float)
        b = np.array([c[1] for c in cles], float)
        if a.std() < 1e-9 or b.std() < 1e-9:
            return None, len(cles)
        return float(np.corrcoef(a, b)[0, 1]), len(cles)

    for tf in TF_CFG:
        d1 = resultats.get(f"BTCUSDT_{tf}", {}).get("_flags_ts")
        d2 = resultats.get(f"ETHUSDT_{tf}", {}).get("_flags_ts")
        if d1 and d2:
            v, nn = phi(d1, d2, tol_s=TF_S[tf] * TF_CFG[tf]["h"])
            out["btc_vs_eth"][tf] = {"phi": v, "n": nn}
    for sym in SYMBOLES:
        ref = resultats.get(f"{sym}_1H", {}).get("_flags_ts")
        if not ref:
            continue
        out["inter_tf_vs_1H"][sym] = {}
        for tf in TF_CFG:
            if tf == "1H":
                continue
            dfin = resultats.get(f"{sym}_{tf}", {}).get("_flags_ts")
            if not dfin:
                continue
            fin_est_plus_fin = TF_S[tf] < TF_S["1H"]
            if fin_est_plus_fin:                      # 1H (grossier) vs flag fin
                v, nn = phi(ref, dfin, tol_s=TF_S[tf] * TF_CFG[tf]["h"])
            else:                                     # TF grossier vs flag 1H
                v, nn = phi(dfin, ref, tol_s=TF_S["1H"] * TF_CFG["1H"]["h"])
            out["inter_tf_vs_1H"][sym][tf] = {"phi": v, "n": nn}
    return out


# ------------------------------------------------------------------ principal

def main():
    resultats = {"meta": {
        "date": time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime()),
        "seed": rf.SEED, "n_seeds_nul": N_SEEDS_NUL, "n_blocs": N_BLOCS,
        "protocole": "walk-forward purgé, échantillons non chevauchants (pas=h), "
                     "bloc 0 amorçage, HMM fit train seul + filtrage forward "
                     "manuel (jamais predict/Viterbi), ruptures fenêtre passée.",
        "config_tf": {tf: {k: (list(v) if isinstance(v, tuple) else v)
                           for k, v in cfg.items()} for tf, cfg in TF_CFG.items()},
    }, "series": {}}
    for sym in SYMBOLES:
        for tf in TF_CFG:
            t0 = time.time()
            try:
                res = traite_serie(sym, tf)
            except Exception as e:
                res = {"statut": f"ERREUR: {type(e).__name__}: {e}"}
            resultats["series"][f"{sym}_{tf}"] = res
            print(f"{sym} {tf}: {res.get('statut')} "
                  f"(prof {res.get('profondeur_jours')} j, "
                  f"n_ech {res.get('n_echantillons')}, {time.time()-t0:.0f}s)",
                  flush=True)
            # écriture incrémentale (sans les flags bruts)
            propre = {k: v for k, v in resultats.items()}
            propre["series"] = {k: {k2: v2 for k2, v2 in v.items()
                                    if k2 != "_flags_ts"}
                                for k, v in resultats["series"].items()}
            SORTIE.write_text(json.dumps(propre, ensure_ascii=False, indent=1),
                              encoding="utf-8")
    resultats["coherence"] = coherence(resultats["series"])
    propre = {k: v for k, v in resultats.items()}
    propre["series"] = {k: {k2: v2 for k2, v2 in v.items() if k2 != "_flags_ts"}
                        for k, v in resultats["series"].items()}
    SORTIE.write_text(json.dumps(propre, ensure_ascii=False, indent=1),
                      encoding="utf-8")
    print("FINI — resultats.json écrit. Lecture seule, aucun ordre.")


if __name__ == "__main__":
    main()
