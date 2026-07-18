"""
stats_hac_dsr_validate.py — VALIDATION des nouveaux outils de mesure d'audit_core
(nw_tstat / expected_max_sharpe / probabilistic_sharpe / deflated_sharpe) contre
des cas ANALYTIQUES connus + Monte-Carlo. Lecture seule, aucun ordre.

Références :
  - Newey-West (1987) HAC ; pour un AR(1) φ : LRV/γ0 = (1+φ)/(1−φ).
  - Bailey & López de Prado (2014) DSR / théorème des fausses stratégies.
"""
import math

import numpy as np

import audit_core as ac

rng = np.random.default_rng(12345)
OK = "✅"; KO = "❌"
fails = 0


def check(name, cond, detail=""):
    global fails
    print(f"  {OK if cond else KO} {name}{('  ' + detail) if detail else ''}")
    if not cond:
        fails += 1


print("1) NEWEY-WEST — i.i.d. gaussien : HAC ≈ OLS (pas d'autocorr à corriger)")
x = rng.standard_normal(4000) * 0.01 + 0.0003
r = ac.nw_tstat(x)
ratio = r["se_nw"] / r["se_ols"]
check("se_nw/se_ols ≈ 1 sous i.i.d.", 0.9 < ratio < 1.15, f"ratio={ratio:.3f}  t_ols={r['t_ols']:.2f} t_nw={r['t_nw']:.2f} lag={r['lag']}")

print("\n2) NEWEY-WEST — AR(1) φ=0.5 : la variance de long terme doit gonfler la SE")
phi = 0.5
n = 6000
e = rng.standard_normal(n) * 0.01
y = np.zeros(n)
for t in range(1, n):
    y[t] = phi * y[t - 1] + e[t]
y += 0.0002
r2 = ac.nw_tstat(y)
theo = (1 + phi) / (1 - phi)                        # ratio LRV/γ0 attendu = 3.0
emp = (r2["se_nw"] / r2["se_ols"]) ** 2             # ratio des variances estimé
check("se_nw > se_ols sous autocorr positive", r2["se_nw"] > r2["se_ols"] * 1.3,
      f"se_nw/se_ols={r2['se_nw']/r2['se_ols']:.2f}")
check("ratio variance ≈ (1+φ)/(1−φ)=3 (ordre de grandeur)", 1.8 < emp < 3.6,
      f"empirique={emp:.2f} vs théorique={theo:.1f}  (t_ols={r2['t_ols']:.2f} -> t_nw={r2['t_nw']:.2f})")

print("\n3) PSR — rendements normaux, SR*=0 : PSR(0) ≈ Φ(SR·√(n−1))")
z = rng.standard_normal(3000) * 0.01 + 0.0008
p = ac.probabilistic_sharpe(z, sr_benchmark=0.0)
sr_bar = p["sr_bar"]
approx = 0.5 * (1 + math.erf((sr_bar * math.sqrt(len(z) - 1)) / (math.sqrt(1 + sr_bar**2 / 2) * math.sqrt(2))))
check("PSR(0) ≈ Φ(sr·√(n−1)/√(1+sr²/2))", abs(p["psr"] - approx) < 0.02,
      f"psr={p['psr']:.4f} approx={approx:.4f} skew={p['skew']:.2f} kurt={p['kurt']:.2f}")

print("\n4) EXPECTED MAX SHARPE — monotone croissant en N")
vs = 1.0 / 2000                                     # var d'un SR par barre sur n=2000 sous H0 ≈ 1/n
seq = [ac.expected_max_sharpe(vs, N) for N in (2, 5, 10, 50, 200)]
check("SR0 strictement croissant avec N", all(a < b for a, b in zip(seq, seq[1:])),
      "  ".join(f"N={N}:{s:.4f}" for N, s in zip((2, 5, 10, 50, 200), seq)))

print("\n5) THÉORÈME DES FAUSSES STRATÉGIES — Monte-Carlo du max de N Sharpe sous H0")
n_bar, N, sims = 2000, 20, 4000
maxes, all_sr = [], []
for _ in range(sims):
    R = rng.standard_normal((N, n_bar))             # N stratégies i.i.d. N(0,1), vrai edge = 0
    sr = R.mean(axis=1) / R.std(axis=1, ddof=1)     # Sharpe PAR BARRE de chaque essai
    all_sr.append(sr)
    maxes.append(sr.max())
all_sr = np.concatenate(all_sr)
var_sr = float(np.var(all_sr, ddof=1))
predicted = ac.expected_max_sharpe(var_sr, N)
realized = float(np.mean(maxes))
rel = abs(predicted - realized) / realized
check("SR0 prédit ≈ max réalisé (Monte-Carlo, écart < 8 %)", rel < 0.08,
      f"prédit={predicted:.4f} réalisé={realized:.4f} (écart {rel*100:.1f} %, var_sr={var_sr:.2e})")

print("\n6) DSR — une VRAIE stratégie (edge réel) doit passer ; du BRUIT sélectionné doit échouer")
# vraie : edge net positif, un seul essai «honnête»
true_r = rng.standard_normal(2500) * 0.01 + 0.0018
d_true = ac.deflated_sharpe(true_r, var_sr=1.0 / 2500, n_trials=1)
check("DSR ≈ PSR(0) élevé pour N=1 edge réel", d_true["dsr"] > 0.95, f"dsr={d_true['dsr']:.4f} sr0={d_true['sr0']:.4f}")
# bruit : on prend le MEILLEUR de N=50 séries de pur bruit -> DSR doit s'effondrer
noise = rng.standard_normal((50, 2500)) * 0.01
sr_noise = noise.mean(axis=1) / noise.std(axis=1, ddof=1)
best = int(np.argmax(sr_noise))
d_noise = ac.deflated_sharpe(noise[best], sr_trials=sr_noise, n_trials=50)
check("DSR effondrée pour le meilleur de 50 séries de bruit", d_noise["dsr"] < 0.60,
      f"dsr={d_noise['dsr']:.4f} sr0={d_noise['sr0']:.4f} (best sr_bar={sr_noise[best]:.4f})")

print("\n" + "=" * 72)
print(f"{'TOUS LES CONTRÔLES PASSENT' if fails == 0 else str(fails) + ' CONTRÔLE(S) EN ÉCHEC'}")
print("=" * 72)
raise SystemExit(1 if fails else 0)
