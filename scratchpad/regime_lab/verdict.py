"""Agrégation-verdict du labo régime (main loop, l'agent a été coupé avant l'écrire)."""
import json, math
import numpy as np

d = json.load(open('scratchpad/regime_lab/resultats.json'))
S = d['series']

print("=== LABO RÉGIME — VERDICT ===")
print(f"protocole: {d['meta'].get('protocole','')[:90]}")
print(f"\n(1) PERTINENCE-VOL : le flag de régime prédit-il |rendement| forward ? (t sur 6 plis)")
print(f"{'série':<14}{'prof_j':>7}{'ic_phaut_t':>12}{'ic_vol_t':>10}{'exces_hmm2_t':>13}")
pert_ts = []
for k, s in S.items():
    if s.get('statut') != 'OK':
        continue
    pv = s.get('pertinence_vol', {})
    t1 = pv.get('ic_phaut_absfwd', {}).get('t')
    t2 = pv.get('ic_vol_absfwd', {}).get('t')
    t3 = pv.get('exces_ratio_absfwd_hmm2', {}).get('t')
    print(f"{k:<14}{s['profondeur_jours']:>7.0f}{(t1 or 0):>12.2f}{(t2 or 0):>10.2f}{(t3 or 0):>13.2f}")
    if t1 is not None: pert_ts.append(t1)
print(f"  -> ic_phaut_absfwd t médian = {np.median(pert_ts):+.2f} (barre |t|>=3) ; "
      f"{sum(1 for t in pert_ts if t>=3)}/{len(pert_ts)} séries >=3")

print(f"\n(2) SÉPARATION DIRECTIONNELLE : le régime sépare-t-il l'IC du signal de réf ? (delta_rang par pli)")
print(f"{'série':<14}{'flag':<12}{'delta_moy':>11}{'t_delta':>9}{'|IC0|~|IC1|':>13}")
best = []
for k, s in S.items():
    if s.get('statut') != 'OK':
        continue
    plis = s.get('plis', [])
    if not plis:
        continue
    for flag in ('hmm2', 'hmm3', 'rupt_recent'):
        deltas = [p[flag]['delta_rang'] for p in plis
                  if p.get(flag) is not None and p[flag].get('delta_rang') is not None]
        if len(deltas) < 3:
            continue
        m = float(np.mean(deltas)); sd = float(np.std(deltas, ddof=1))
        t = m / (sd / math.sqrt(len(deltas))) if sd > 1e-9 else 0.0
        best.append((abs(t), k, flag, m, t))
best.sort(reverse=True)
for abst, k, flag, m, t in best[:8]:
    print(f"{k:<14}{flag:<12}{m:>+11.4f}{t:>9.2f}")
seps = [b[0] for b in best]
print(f"  -> |t_delta| max = {max(seps):.2f} sur {len(best)} (série×flag) ; "
      f"{sum(1 for x in seps if x>=3)} au-dessus de 3")
print("\nLecture seule. Aucun ordre.")
