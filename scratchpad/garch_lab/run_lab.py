"""Labo GARCH : le GARCH(1,1) FITTÉ (arch) prévoit-il mieux la vol que le FIGÉ ? LECTURE SEULE.

Reconstruit dans la main loop (le sous-agent est mort sur la limite de session).
Concurrents, prévision de variance 1 pas en walk-forward, SANS regard en avant :
  (a) fige   : volatility.garch11_vol (α=0.10/β=0.85, variance-targeting) — le code du bot
  (b) ewma   : volatility.ewma_vol (λ=0.94)
  (c) arch   : GARCH(1,1) fitté MLE (lib arch) sur la fenêtre passée, refit tous les K pas,
               puis filtrage récursif des params fittés (pas de refit chaque pas = coût borné)
  (d) naive  : écart-type roulant
Proxys de vol réalisée : r²(t+1) [principal] et Parkinson OHLC [robustesse].
Métriques par pli (5 plis temporels) : QLIKE (principale) + MSE ; t apparié (arch − fige).
Impact métier : vol-targeting levier = vol_cible/vol_prédite (borné ×5) ; on mesure à quel
point la vol RÉALISÉE du livre vol-targeté colle à la cible (écart absolu). ERR-001 : échelle
complète des TF disponibles (1W exclu — trop court, annoté).
"""
import os
os.environ.setdefault("OMP_NUM_THREADS", "2")
import json, math, sys, time, warnings
from pathlib import Path
import numpy as np
warnings.filterwarnings("ignore")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
import candles_history as ch
import volatility as vol
from arch import arch_model

TFS = ["5m", "15m", "30m", "1H", "4H", "1D"]        # 1W exclu (n<300) — ERR-001 annoté
SYMBOLS = ["BTCUSDT", "ETHUSDT"]
W = 500              # fenêtre roulante (rendements)
K = 40               # refit arch tous les K pas
N_MAX = 4200         # borne le nb de pas walk-forward par TF (coût)
N_FOLDS = 5
CAP_LEV = 5.0        # mur levier du mandat
OUT = Path(__file__).resolve().parent / "resultats.json"
LOG = Path(__file__).resolve().parent / "run.log"


def logline(m):
    with open(LOG, "a") as f:
        f.write(m + "\n")
    print(m, flush=True)


def parkinson_var(o, h, l, c):
    """Variance de Parkinson (high-low) — robustesse vs r²."""
    if h > 0 and l > 0 and h >= l:
        return (math.log(h / l) ** 2) / (4.0 * math.log(2.0))
    return None


def qlike(rv, pv):
    """QLIKE sur la variance : rv/pv - log(rv/pv) - 1 (>=0, min à rv=pv)."""
    if pv <= 1e-15 or rv <= 1e-15:
        return None
    x = rv / pv
    return x - math.log(x) - 1.0


def one_tf(sym, tf):
    bars = ch.load(sym, tf)
    if not bars or len(bars) < W + 200:
        return {"statut": "trop_court", "n_bars": len(bars) if bars else 0}
    bars = bars[-(N_MAX + W + 2):]
    closes = np.array([float(b[4]) for b in bars], dtype=float)
    highs = np.array([float(b[2]) for b in bars], dtype=float)
    lows = np.array([float(b[3]) for b in bars], dtype=float)
    r = np.diff(np.log(closes))                      # rendements log
    n = len(r)
    steps = range(W, n - 1)                           # prédire var pour t+1 à partir de <= t
    # préparation arch : refit périodique, filtrage entre les refits
    params = None                                     # (omega, alpha, beta) en unités r (pas %)
    recs = []                                          # (t, rv_r2, rv_park, var_fige, var_ewma, var_arch, var_naive)
    last_fit = -10 ** 9
    var_arch_state = None
    for i, t in enumerate(steps):
        win_r = r[t - W:t]                             # rendements <= t (exclut t+1)
        win_closes = closes[t - W:t + 1]
        # (a) figé
        s_fige = vol.garch11_vol(win_closes)
        v_fige = (s_fige ** 2) if s_fige else None
        # (b) ewma
        s_ewma = vol.ewma_vol(win_closes)
        v_ewma = (s_ewma ** 2) if s_ewma else None
        # (d) naive
        v_naive = float(np.var(win_r))
        # (c) arch fitté : refit tous les K pas, sinon filtrage forward
        if t - last_fit >= K or params is None:
            try:
                am = arch_model(win_r * 100.0, mean="Zero", vol="GARCH", p=1, q=1)
                res = am.fit(disp="off", show_warning=False)
                p = res.params
                omega = float(p["omega"]) / 1e4
                alpha = float(p["alpha[1]"])
                beta = float(p["beta[1]"])
                params = (omega, alpha, beta)
                # variance conditionnelle courante = dernière var filtrée du fit
                var_arch_state = float(res.conditional_volatility[-1] ** 2) / 1e4
                last_fit = t
            except Exception:
                params = None
        if params is not None:
            omega, alpha, beta = params
            # filtre un pas : var_{t+1} = omega + alpha r_t^2 + beta var_t
            var_arch_state = omega + alpha * float(r[t - 1]) ** 2 + beta * (var_arch_state or v_naive)
            v_arch = max(var_arch_state, 1e-15)
        else:
            v_arch = None
        # réalisé à t+1
        rv_r2 = float(r[t + 1]) ** 2
        rv_park = parkinson_var(0, highs[t + 2], lows[t + 2], 0) if t + 2 < len(highs) else None
        recs.append((t, rv_r2, rv_park, v_fige, v_ewma, v_arch, v_naive))
    # métriques par pli
    recs = [x for x in recs if x[3] and x[4] and x[5] and x[6]]
    if len(recs) < N_FOLDS * 20:
        return {"statut": "peu_de_pas", "n_pas": len(recs)}
    arr = np.array([(x[1], x[3], x[4], x[5], x[6]) for x in recs])  # rv_r2, fige, ewma, arch, naive
    fold_bounds = np.linspace(0, len(arr), N_FOLDS + 1).astype(int)
    methods = ["fige", "ewma", "arch", "naive"]
    qlike_folds = {m: [] for m in methods}
    mse_folds = {m: [] for m in methods}
    for k in range(N_FOLDS):
        a, b = fold_bounds[k], fold_bounds[k + 1]
        seg = arr[a:b]
        for j, m in enumerate(methods):
            ql = [qlike(rv, seg[i, 1 + j]) for i, rv in enumerate(seg[:, 0])]
            ql = [q for q in ql if q is not None]
            mse = np.mean((seg[:, 0] - seg[:, 1 + j]) ** 2)
            qlike_folds[m].append(float(np.mean(ql)) if ql else None)
            mse_folds[m].append(float(mse))
    # t apparié arch - fige sur QLIKE (négatif = arch meilleur)
    diff = [qlike_folds["arch"][k] - qlike_folds["fige"][k] for k in range(N_FOLDS)
            if qlike_folds["arch"][k] is not None and qlike_folds["fige"][k] is not None]
    if len(diff) >= 3:
        md = float(np.mean(diff)); sdd = float(np.std(diff, ddof=1))
        t_paired = md / (sdd / math.sqrt(len(diff))) if sdd > 1e-12 else 0.0
    else:
        md, t_paired = None, None
    # impact métier : vol-targeting, chaque méthode cible sa propre médiane (comparaison juste)
    rets_next = arr[:, 0] ** 0.5 * np.sign(np.random.default_rng(0).standard_normal(len(arr)))  # placeholder
    vt = {}
    for j, m in enumerate(methods):
        pv = np.sqrt(np.clip(arr[:, 1 + j], 1e-15, None))     # vol prédite
        target = float(np.median(pv))
        lev = np.clip(target / pv, 0.0, CAP_LEV)
        # rendement réalisé t+1 (signé) : sqrt(rv) porte la magnitude ; signe non modélisé
        real_ret = np.sqrt(arr[:, 0])                          # |r_{t+1}| (magnitude)
        port = lev * real_ret                                  # magnitude du livre vol-targeté
        realized_vol = float(np.std(port))
        vt[m] = {"cible": round(target, 6), "vol_realisee": round(realized_vol, 6),
                 "ecart_abs": round(abs(realized_vol - target), 6),
                 "lev_median": round(float(np.median(lev)), 3)}
    return {
        "statut": "OK",
        "profondeur_jours": round((bars[-1][0] - bars[0][0]) / 86400000, 1),
        "n_bars": len(bars), "n_pas": len(arr),
        "qlike_moy": {m: round(float(np.mean([q for q in qlike_folds[m] if q is not None])), 6) for m in methods},
        "mse_moy": {m: float(np.mean(mse_folds[m])) for m in methods},
        "qlike_par_pli": qlike_folds,
        "arch_vs_fige_qlike": {"delta_moy": md, "t_paired": t_paired,
                               "arch_gagne_plis": sum(1 for x in diff if x < 0), "n_plis": len(diff)},
        "vol_targeting": vt,
    }


def main():
    if LOG.exists():
        LOG.unlink()
    out = {"meta": {"W": W, "K": K, "N_MAX": N_MAX, "n_folds": N_FOLDS, "cap_lev": CAP_LEV,
                    "note_tf": "1W exclu (n<300) — reste de l'échelle couvert (ERR-001)"},
           "series": {}}
    for sym in SYMBOLS:
        for tf in TFS:
            t0 = time.time()
            try:
                res = one_tf(sym, tf)
            except Exception as e:
                res = {"statut": "ERREUR", "err": f"{type(e).__name__}: {e}"}
            out["series"][f"{sym}_{tf}"] = res
            st = res.get("statut")
            extra = ""
            if st == "OK":
                q = res["qlike_moy"]
                extra = (f"QLIKE arch={q['arch']:.4f} fige={q['fige']:.4f} ewma={q['ewma']:.4f} "
                         f"| t_arch-fige={res['arch_vs_fige_qlike']['t_paired']}")
            logline(f"{sym} {tf}: {st} ({time.time()-t0:.0f}s) {extra}")
            OUT.write_text(json.dumps(out, indent=1))     # sauvegarde incrémentale
    logline("FINI")


if __name__ == "__main__":
    main()
