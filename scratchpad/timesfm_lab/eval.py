"""Éval HONNÊTE de TimesFM zero-shot sur les vraies bougies BTC — échelle COMPLÈTE de TF
(ERR-001), net de frais. Tourne avec le venv ISOLÉ (ERR-004). Données dumpées par le
Python système dans data/{TF}.json (closes réels du cache Bitget).

Question mesurée : le forecast 1-pas de TimesFM a-t-il un IC directionnel sur les rendements
crypto intraday, et bat-il les frais (~6 bps/côté) ? Prior : NON (rendements quasi-aléatoires).
"""
import json, os, math, sys
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")
TFS = ["M1", "M5", "M15", "M30", "H1", "H4", "D1", "W1"]
FEE_ROUNDTRIP = 0.0012          # ~6 bps/côté taker × 2 (entrée+sortie) — seuil à battre
N_EVAL = 120                    # screening rapide (t-stat ~sqrt(120) : détecte tout IC réel), léger pour le bot LIVE
PATCH = 32                      # input_patch_len TimesFM v1 -> context multiple de 32


def spearman(a, b):
    a, b = np.asarray(a, float), np.asarray(b, float)
    if len(a) < 3:
        return float("nan")
    ra = np.argsort(np.argsort(a)); rb = np.argsort(np.argsort(b))
    ra = (ra - ra.mean()); rb = (rb - rb.mean())
    d = math.sqrt((ra**2).sum() * (rb**2).sum())
    return float((ra * rb).sum() / d) if d > 0 else float("nan")


HORIZON = 8

def load_model():
    # API TimesFM 2.5 (introspectée le 2026-07-10 dans le venv : TimesFM_2p5_200M_torch
    # .from_pretrained(repo) -> .compile(ForecastConfig) -> .forecast(horizon, inputs)).
    import timesfm
    M = timesfm.TimesFM_2p5_200M_torch
    model = M.from_pretrained(M.DEFAULT_REPO_ID)
    model.compile(timesfm.ForecastConfig(max_context=256, max_horizon=HORIZON,
                                         normalize_inputs=True, per_core_batch_size=32,
                                         use_continuous_quantile_head=True))
    print(f"  modèle chargé : {M.DEFAULT_REPO_ID} (TimesFM 2.5)")
    return model


def eval_tf(tfm, tf):
    d = json.load(open(os.path.join(DATA, f"{tf}.json")))
    closes = np.asarray(d["closes"], float)
    n = len(closes)
    ctx = min(256, ((n // 2) // PATCH) * PATCH)
    if ctx < PATCH or n < ctx + 20:
        return {"tf": tf, "n": n, "note": "série trop courte"}
    idx = list(range(ctx, n - 1))
    if len(idx) > N_EVAL:
        idx = list(np.linspace(ctx, n - 2, N_EVAL, dtype=int))
    inputs = [closes[i - ctx:i] for i in idx]
    last = np.array([closes[i - 1] for i in idx])
    actual = np.array([closes[i] for i in idx])
    fc, _ = tfm.forecast(horizon=HORIZON, inputs=inputs)
    pred = np.asarray(fc)[:, 0]
    pred_ret = (pred - last) / last
    real_ret = (actual - last) / last
    ic = spearman(pred_ret, real_ret)
    m = len(idx)
    t = ic * math.sqrt(max(m - 2, 1)) / math.sqrt(max(1 - ic * ic, 1e-9)) if ic == ic else float("nan")
    hit = float(np.mean(np.sign(pred_ret) == np.sign(real_ret)))
    strat = np.sign(pred_ret) * real_ret                 # rendement dirigé par le forecast
    net = strat - FEE_ROUNDTRIP
    return {"tf": tf, "n": n, "ctx": ctx, "m": m, "ic": round(ic, 4), "t": round(t, 2),
            "hit%": round(100 * hit, 1), "gross_bps": round(1e4 * strat.mean(), 2),
            "net_bps": round(1e4 * net.mean(), 2)}


def main():
    print("=== TimesFM zero-shot — IC directionnel net de frais (BTC, échelle complète) ===")
    tfm = load_model()
    rows = []
    for tf in TFS:
        try:
            r = eval_tf(tfm, tf)
        except Exception as e:
            r = {"tf": tf, "note": f"ERREUR {type(e).__name__} {str(e)[:80]}"}
        rows.append(r)
        print("  ", r)
    print()
    print(f"{'TF':4s} {'m':>4s} {'RankIC':>7s} {'t':>6s} {'hit%':>6s} {'gross_bps':>9s} {'net_bps':>8s}")
    for r in rows:
        if "ic" in r:
            print(f"{r['tf']:4s} {r['m']:4d} {r['ic']:7.4f} {r['t']:6.2f} {r['hit%']:6.1f} "
                  f"{r['gross_bps']:9.2f} {r['net_bps']:8.2f}")
        else:
            print(f"{r['tf']:4s}  -> {r.get('note')}")
    json.dump(rows, open(os.path.join(HERE, "results.json"), "w"), indent=2)
    # verdict synthétique
    valides = [r for r in rows if "ic" in r]
    net_pos = [r for r in valides if r["net_bps"] > 0 and r["t"] > 2]
    print()
    print(f"VERDICT : {len(net_pos)}/{len(valides)} TF avec net>0 ET |t|>2 "
          f"(IC directionnel significatif ET battant les frais).")
    print("  -> " + ("PISTE : " + ", ".join(r["tf"] for r in net_pos) if net_pos
                     else "RIEN à brancher (conforme au prior : rendements crypto ~aléatoires + mur des frais)."))


if __name__ == "__main__":
    main()
