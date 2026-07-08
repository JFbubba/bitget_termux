"""Agrégation de resultats.json -> tableau de synthèse + verdict par feature.

Barre de promotion (mission) : |t| >= 3 de façon COHÉRENTE entre plis (signe stable)
ET entre TFs (même signe sur les TFs où |t|>=2, au moins 2 TFs à |t|>=3).
LECTURE SEULE de resultats.json ; écrit synthese.json.
"""
import json
from collections import defaultdict
from pathlib import Path

LAB = Path(__file__).resolve().parent
res = json.loads((LAB / "resultats.json").read_text())

TF_ORDER = ["1m", "5m", "15m", "30m", "1H", "4H", "1D", "1W"]
rows = defaultdict(lambda: defaultdict(list))   # feature -> tf -> [(sym, h, dict)]

for tf, syms in res["tables"].items():
    for sym, feats in syms.items():
        for feat, per_h in feats.items():
            for h, r in per_h.items():
                rows[feat][tf].append((sym, h, r))

synth = {}
for feat, tfs in sorted(rows.items()):
    per_tf = {}
    for tf in TF_ORDER:
        if tf not in tfs:
            continue
        cells = tfs[tf]
        ic_r = [r["ic_r"] for _, _, r in cells]
        ic_p = [r["ic_p"] for _, _, r in cells]
        t_r = [r["t_r"] for _, _, r in cells]
        t_p = [r["t_p"] for _, _, r in cells]
        b_r = [r["base_ic_r"] for _, _, r in cells]
        # cohérence de signe entre plis, pire cellule
        sign_coh = []
        for _, _, r in cells:
            f_ic = [f["ic_r"] for f in r["folds"]]
            pos = sum(1 for x in f_ic if x > 0)
            sign_coh.append(max(pos, len(f_ic) - pos) / len(f_ic))
        per_tf[tf] = {
            "n_cells": len(cells),
            "ic_r_moy": round(sum(ic_r) / len(ic_r), 4),
            "ic_p_moy": round(sum(ic_p) / len(ic_p), 4),
            "t_r_min": round(min(t_r, key=abs), 2), "t_r_max": round(max(t_r, key=abs), 2),
            "t_r_all": [round(t, 2) for t in t_r],
            "t_p_all": [round(t, 2) for t in t_p],
            "base_ic_r_moy": round(sum(b_r) / len(b_r), 4),
            "coh_plis_min": round(min(sign_coh), 2),
            "detail": [{"sym": s, "h": h, "ic_r": r["ic_r"], "t_r": r["t_r"],
                        "ic_p": r["ic_p"], "t_p": r["t_p"], "n": r["n_tot"],
                        "base_ic_r": r["base_ic_r"], "base_t_r": r["base_t_r"],
                        "vol_ic_r": r["vol_ic_r"], "vol_t_r": r["vol_t_r"]}
                       for s, h, r in cells],
        }
    # barre de promotion (sur l'IC de RANG, métrique §96 des dashboards)
    strong = []   # (tf, t) avec |t|>=3
    for tf, d in per_tf.items():
        for t in d["t_r_all"]:
            if abs(t) >= 3:
                strong.append((tf, t))
    tfs_strong = sorted({tf for tf, _ in strong})
    signs = {1 if t > 0 else -1 for _, t in strong}
    n_cells_tot = sum(d["n_cells"] for d in per_tf.values())
    n_strong = len(strong)
    promu = (len(tfs_strong) >= 2 and len(signs) == 1
             and n_strong >= max(3, 0.25 * n_cells_tot))
    synth[feat] = {"per_tf": per_tf, "cells_t3": n_strong, "cells_total": n_cells_tot,
                   "tfs_avec_t3": tfs_strong, "signes_t3": sorted(signs),
                   "candidate": bool(promu)}

(LAB / "synthese.json").write_text(json.dumps(synth, indent=1))

# tableau texte
print(f"{'feature':<26}{'TF':<5}{'ic_rg':>8}{'ic_pe':>8}{'t_rg (cellules)':>34}"
      f"{'coh':>6}{'base_rg':>9}")
for feat, s in synth.items():
    first = True
    for tf in TF_ORDER:
        if tf not in s["per_tf"]:
            continue
        d = s["per_tf"][tf]
        print(f"{feat if first else '':<26}{tf:<5}{d['ic_r_moy']:>+8.3f}"
              f"{d['ic_p_moy']:>+8.3f}{str(d['t_r_all']):>34}{d['coh_plis_min']:>6.2f}"
              f"{d['base_ic_r_moy']:>+9.3f}")
        first = False
    print(f"{'':<26}==> cellules |t|>=3 : {s['cells_t3']}/{s['cells_total']} "
          f"sur TFs {s['tfs_avec_t3']} signes {s['signes_t3']} "
          f"-> {'CANDIDATE' if s['candidate'] else 'rejetée'}")
    print()
