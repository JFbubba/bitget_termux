"""Canal VOLATILITÉ/RÉGIME : IC des features vs |rendement forward| (pas le signe).
C'est le test CORRECT pour des mesures direction-agnostiques (forme, rugosité,
intrication) — celui qui reflète l'usage réel de l'agent (gate de régime).
On agrège vol_ic_r / vol_t_r déjà stockés par pli dans resultats.json.
Barre : |t| >= 3 cohérent (signe stable) sur >=2 TFs. LECTURE SEULE."""
import json
from collections import defaultdict
from pathlib import Path

LAB = Path(__file__).resolve().parent
res = json.loads((LAB / "resultats.json").read_text())
TF_ORDER = ["1m", "5m", "15m", "30m", "1H", "4H", "1D", "1W"]

# recompute per-fold vol t robustly from folds (vol_ic_r stored per fold as 'vol_r')
rows = defaultdict(lambda: defaultdict(list))
for tf, syms in res["tables"].items():
    for sym, feats in syms.items():
        for feat, per_h in feats.items():
            for h, r in per_h.items():
                # t de vol sur les plis
                import numpy as np
                vr = np.array([f["vol_r"] for f in r["folds"]])
                if len(vr) >= 4:
                    se = vr.std(ddof=1) / (len(vr) ** 0.5)
                    t = float(vr.mean() / se) if se > 1e-12 else 0.0
                    rows[feat][tf].append((sym, h, round(float(vr.mean()), 4), round(t, 2)))

print(f"{'feature':<24}{'TF':<5}{'vol_ic_moy':>11}{'  t_vol par cellule (sym×h)'}")
verdicts = {}
for feat in sorted(rows):
    tfs_strong = set(); signs = set(); ncells = 0; nstrong = 0
    lines = []
    for tf in TF_ORDER:
        if tf not in rows[feat]:
            continue
        cells = rows[feat][tf]
        ics = [c[2] for c in cells]; ts = [c[3] for c in cells]
        ncells += len(cells)
        for _, _, ic, t in cells:
            if abs(t) >= 3:
                nstrong += 1; tfs_strong.add(tf); signs.add(1 if ic > 0 else -1)
        lines.append((tf, sum(ics) / len(ics), ts))
    for tf, icm, ts in lines:
        print(f"{feat:<24}{tf:<5}{icm:>+11.4f}   {ts}")
    promu = len(tfs_strong) >= 2 and len(signs) == 1 and nstrong >= max(3, 0.25 * ncells)
    verdicts[feat] = (nstrong, ncells, sorted(tfs_strong), sorted(signs), promu)
    print(f"{'':<24}==> |t_vol|>=3 : {nstrong}/{ncells} TFs {sorted(tfs_strong)} "
          f"signes {sorted(signs)} -> {'CANDIDAT RÉGIME/VOL' if promu else 'rejeté'}\n")

(LAB / "synthese_vol.json").write_text(json.dumps(
    {k: {"n_strong": v[0], "n_cells": v[1], "tfs": v[2], "signs": v[3], "candidate": v[4]}
     for k, v in verdicts.items()}, indent=1))
