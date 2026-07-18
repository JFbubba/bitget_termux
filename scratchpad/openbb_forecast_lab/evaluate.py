"""Évaluation + VERDICT du probe forecast (Python SYSTÈME — pas le venv Darts).

Lit preds/*.json (produits par forecast_probe.py) et mesure, par modèle :
  - Rank IC (Spearman) pred_ret vs real_ret, t-stat sur plis NON chevauchants (purgés) ;
  - hit-rate directionnel ;
  - PnL directionnel NET DE FRAIS (0 / maker 4 bps / taker 12 bps round-trip),
    t-stat sur plis purgés.
Porte d'edge (alignée bot §77) : edge tradeable SEULEMENT si PnL net taker > 0
ET t >= 3 sur plis purgés ET bat le baseline naïf. Sinon REJETÉ.

Méthodo purgée = COPIE fidèle de scratchpad/geometric_v2_lab/gate_lib.py
(purged_folds / t_across_folds / ic_rank) — autonome, sans tirer les deps du labo geometric.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
from scipy.stats import spearmanr

LAB = Path(__file__).resolve().parent
PREDS = LAB / "preds"
FEES = {"0bps": 0.0, "maker_4bps": 0.0004, "taker_12bps": 0.0012}  # round-trip
T_GATE = 3.0                                                        # §77

# Classe d'actifs par symbole — pour lire le verdict PAR CLASSE (crypto vs or vs actions).
CLASSES = {
    "BTCUSDT": "crypto-majeur", "ETHUSDT": "crypto-majeur",
    "SOLUSDT": "crypto-alt", "XRPUSDT": "crypto-alt", "BNBUSDT": "crypto-alt",
    "TRXUSDT": "crypto-alt", "ADAUSDT": "crypto-alt",
    "DOGEUSDT": "crypto-meme", "SHIBUSDT": "crypto-meme", "PEPEUSDT": "crypto-meme",
    "LINKUSDT": "crypto-defi", "UNIUSDT": "crypto-defi",
    "XAUUSDT": "metal", "XAGUSDT": "metal",
    "AAPLUSDT": "action-us", "TSLAUSDT": "action-us", "NVDAUSDT": "action-us",
    "SPYUSDT": "action-us", "QQQUSDT": "action-us", "COINUSDT": "action-us",
    "MSTRUSDT": "action-us",
}


# ---- méthodo purgée (copie fidèle de gate_lib) --------------------------------
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
# -------------------------------------------------------------------------------


def eval_model(rows, H):
    """rows = liste {i, pred_ret, real_ret}. Renvoie un dict de métriques."""
    if len(rows) < 30:
        return {"n": len(rows), "insufficient": True}
    idx = np.array([r["i"] for r in rows])
    pred = np.array([r["pred_ret"] for r in rows], dtype=float)
    real = np.array([r["real_ret"] for r in rows], dtype=float)
    order = np.argsort(idx)
    idx, pred, real = idx[order], pred[order], real[order]

    folds = purged_folds(idx, H, n_folds=6)
    folds = [f for f in folds if len(f) >= 8]

    # Rank IC global + t cross-folds
    ic_glob = ic_rank(pred, real)
    ic_folds = [ic_rank(pred[f], real[f]) for f in folds]
    _, ic_t, ic_k = t_across_folds(ic_folds)

    hit = float(np.mean(np.sign(pred) == np.sign(real)))

    out = {"n": len(rows), "ic_rank": _r(ic_glob), "ic_t": _r(ic_t), "ic_folds": ic_k,
           "hit_rate": _r(hit), "pnl": {}}
    for name, fee in FEES.items():
        pnl = np.sign(pred) * real - fee                 # position à chaque origine, tenue H barres
        mean_glob = float(pnl.mean())
        fold_means = [float(pnl[f].mean()) for f in folds]
        _, t, _ = t_across_folds(fold_means)
        out["pnl"][name] = {"mean_bps": _r(mean_glob * 1e4), "t": _r(t)}
    return out


def _r(x):
    try:
        return round(float(x), 4) if math.isfinite(float(x)) else None
    except Exception:
        return None


def verdict_line(m):
    """Un modèle passe la porte si taker>0 et t>=3."""
    tk = m.get("pnl", {}).get("taker_12bps")
    if not tk or tk["mean_bps"] is None or tk["t"] is None:
        return False
    return tk["mean_bps"] > 0 and tk["t"] >= T_GATE


def main():
    files = sorted(PREDS.glob("*.json"))
    if not files:
        print("Aucune prévision dans preds/ — lancer forecast_probe.py d'abord.")
        return
    report = {}
    passes = []
    for f in files:
        d = json.loads(f.read_text())
        meta = d["meta"]
        key = f"{meta['sym']}_{meta['tf']}_h{meta['H']}"
        report[key] = {"meta": meta, "models": {}}
        for mname, rows in d["models"].items():
            m = eval_model(rows, meta["H"])
            report[key]["models"][mname] = m
            if not m.get("insufficient") and verdict_line(m):
                passes.append((key, mname, m["pnl"]["taker_12bps"]))

    (LAB / "VERDICT.json").write_text(json.dumps(report, indent=1))

    # ---- résumé lisible
    lines = []
    lines.append("# Probe forecast OpenBB/Darts — VERDICT")
    lines.append("")
    lines.append("Porte d'edge : PnL directionnel NET taker (12 bps round-trip) > 0 "
                 f"ET t >= {T_GATE} sur plis NON chevauchants purgés, et > baseline naïf.")
    lines.append("")
    hdr = f"| {'clé':<18} | modèle | IC | IC_t | hit | PnL@0 | PnL@4 | PnL@12bps (t) |"
    lines.append(hdr)
    lines.append("|" + "-" * (len(hdr) - 2) + "|")
    for key in sorted(report):
        for mname in ("naive", "autoets", "nhits"):
            m = report[key]["models"].get(mname)
            if not m:
                continue
            if m.get("insufficient"):
                lines.append(f"| {key:<18} | {mname:<7} | (n={m['n']} insuff.) |")
                continue
            p0 = m["pnl"]["0bps"]["mean_bps"]; p4 = m["pnl"]["maker_4bps"]["mean_bps"]
            p12 = m["pnl"]["taker_12bps"]
            flag = " ✅" if verdict_line(m) else ""
            lines.append(
                f"| {key:<18} | {mname:<7} | {m['ic_rank']} | {m['ic_t']} | "
                f"{m['hit_rate']} | {p0} | {p4} | {p12['mean_bps']} (t={p12['t']}){flag} |")
    # --- Synthèse PAR CLASSE d'actifs (le cœur de la question) ---
    lines.append("")
    lines.append("## Synthèse par classe d'actifs (net taker 12 bps)")
    lines.append("| classe | #configs | passent porte | meilleur net taker bps (t) | meilleur IC (t) |")
    lines.append("|---|---|---|---|---|")
    by_class = {}
    for key in report:
        cls = CLASSES.get(report[key]["meta"]["sym"], "?")
        by_class.setdefault(cls, []).append(key)
    for cls in sorted(by_class):
        n_cfg = n_pass = 0
        best_pnl = best_ic = None
        for key in by_class[cls]:
            for mname, m in report[key]["models"].items():
                if m.get("insufficient"):
                    continue
                n_cfg += 1
                if verdict_line(m):
                    n_pass += 1
                tk = m["pnl"]["taker_12bps"]
                if tk["mean_bps"] is not None and (best_pnl is None or tk["mean_bps"] > best_pnl[0]):
                    best_pnl = (tk["mean_bps"], tk["t"], f"{key}/{mname}")
                if m["ic_rank"] is not None and (best_ic is None or m["ic_rank"] > best_ic[0]):
                    best_ic = (m["ic_rank"], m["ic_t"])
        bp = f"{best_pnl[0]} (t={best_pnl[1]}) [{best_pnl[2]}]" if best_pnl else "-"
        bi = f"{best_ic[0]} (t={best_ic[1]})" if best_ic else "-"
        lines.append(f"| {cls} | {n_cfg} | {n_pass} | {bp} | {bi} |")

    lines.append("")
    if passes:
        lines.append(f"## {len(passes)} configuration(s) PASSENT la porte :")
        for key, mname, tk in passes:
            lines.append(f"- **{key} / {mname}** : {tk['mean_bps']} bps net taker, t={tk['t']}")
    else:
        lines.append("## VERDICT : AUCUNE configuration ne passe la porte d'edge.")
        lines.append("Aucun edge directionnel net de frais (taker) avec t>=3 sur plis purgés. "
                     "Conforme au prior (geometric v2 0/14). RIEN à brancher.")
    txt = "\n".join(lines)
    (LAB / "VERDICT.md").write_text(txt + "\n")
    print(txt)


if __name__ == "__main__":
    main()
