"""Calibration : est-ce que j'UTILISE bien POT/dcor/nolds ? On confronte chaque
feature à des vérités connues (distributions/processus à réponse théorique).
LECTURE SEULE."""
import sys
from pathlib import Path
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import features_v2 as fv

rng = np.random.default_rng(0)
N = 4000

print("=== W1 à la gaussienne (POT) — attendu: gauss≈0.06, t4≈0.15, t2.5≈0.24, uniforme≈0.06 ===")
for name, x in [("gaussien", rng.standard_normal(N)),
                ("t(2.5) lourd", rng.standard_t(2.5, N)),
                ("t(4)", rng.standard_t(4, N)),
                ("uniforme", rng.uniform(-1, 1, N))]:
    # moyenne sur des fenêtres de 160 (comme le live)
    vals = [fv.w1_gauss_pot(x[i:i+160]) for i in range(0, N-160, 160)]
    print(f"  {name:<14} W1_gauss = {np.nanmean(vals):.3f}")

print("\n=== dcor — attendu: identique=1.0, indépendant≈0 (petit biais +), y=x^2 sur [-1,1] fort ===")
a = rng.standard_normal(N)
print(f"  dcor(x, x)            = {fv.dcor_pair(a, a):.3f}")
print(f"  dcor(x, indépendant)  = {fv.dcor_pair(a, rng.standard_normal(N)):.3f}")
u = rng.uniform(-1, 1, N)
print(f"  dcor(u, u^2) [pearson≈0 mais dépendance forte] = {fv.dcor_pair(u, u**2):.3f}"
      f"  (pearson={np.corrcoef(u, u**2)[0,1]:+.3f}, dcor_excess={fv.dcor_excess(u, u**2):+.3f})")

print("\n=== nolds sur processus connus (fenêtre 500) ===")
# marche aléatoire (H≈1.5 pour dfa sur la SÉRIE ; sur INCRÉMENTS H≈0.5)
incr = rng.standard_normal(500)                       # bruit blanc: DFA≈0.5, Hurst≈0.5
walk = np.cumsum(incr)
print(f"  DFA(bruit blanc)      = {fv.nolds_dfa(incr):.3f}  (attendu ≈0.5)")
print(f"  DFA(marche aléatoire) = {fv.nolds_dfa(walk):.3f}  (attendu ≈1.5)")
print(f"  hurst_rs(bruit blanc) = {fv.nolds_hurst_rs(incr):.3f}  (attendu ≈0.5)")
print(f"  sampen(bruit blanc)   = {fv.nolds_sampen(incr):.3f}  (attendu ~2.0-2.3)")
print(f"  sampen(sinus lisse)   = {fv.nolds_sampen(np.sin(np.linspace(0,60,500))):.3f}  (attendu ~0, prévisible)")
print(f"  corr_dim(bruit blanc) = {fv.nolds_corr_dim(incr):.3f}")

print("\n=== W1 dérive: fenêtres du MÊME processus vs processus DÉCALÉ ===")
x = rng.standard_normal(320)
print(f"  w1_drift(même loi)          = {fv.w1_drift(x[:160], x[160:]):.3f}  (attendu petit)")
y = np.concatenate([rng.standard_normal(160), rng.standard_normal(160)*3+2])  # shift moyenne+vol
print(f"  w1_drift(shift moy+vol)     = {fv.w1_drift(y[:160], y[160:]):.3f}  (attendu grand)")
