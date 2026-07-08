"""Agrégation-verdict du labo geometric v2 (main loop, agent coupé avant l'écrire)."""
import json
import numpy as np

d = json.load(open('scratchpad/geometric_v2_lab/resultats.json'))
T = d['tables']
tfs = list(T.keys())
print("=== LABO GEOMETRIC v2 — VERDICT ===")
print(f"TFs bouclés: {tfs}  (ERR-001: {'INCOMPLET — 1 seul TF' if len(tfs)==1 else 'échelle multiple'})")
print(f"fenêtre={d['meta']['window_returns']} · horizons={d['meta']['horizons']} · folds={d['meta']['n_folds']}")

FEATURES = ['geom_vote', 'w1_gauss_pot', 'w1_drift', 'w1_drift_shape',
            'nolds_dfa', 'nolds_hurst_rs', 'nolds_sampen', 'nolds_corr_dim',
            'dcor_excess_btc_eth']
print(f"\n{'feature':<20}{'sym':<5}{'h':<5}{'ic_r':>8}{'t_r':>7}{'ic_p':>8}{'t_p':>7}{'candidate?':>11}")
promus = []
for tf in tfs:
    for sym in T[tf]:
        for feat in FEATURES:
            node = T[tf][sym].get(feat)
            if not node:
                continue
            for h in ('h1', 'h4', 'h24'):
                hn = node.get(h)
                if not hn:
                    continue
                tr, tp = hn.get('t_r'), hn.get('t_p')
                # barre : |t| >= 3 sur rang OU pearson
                cand = (abs(tr or 0) >= 3) or (abs(tp or 0) >= 3)
                if feat == 'geom_vote':  # baseline, jamais "promue"
                    cand_txt = 'BASELINE'
                else:
                    cand_txt = 'OUI' if cand else '-'
                    if cand:
                        promus.append((feat, sym, h, tr, tp))
                # n'imprimer que baseline + les |t|>=2 pour rester lisible
                if feat == 'geom_vote' or abs(tr or 0) >= 2 or abs(tp or 0) >= 2:
                    print(f"{feat:<20}{sym:<5}{h:<5}{(hn.get('ic_r') or 0):>+8.4f}{(tr or 0):>7.2f}"
                          f"{(hn.get('ic_p') or 0):>+8.4f}{(tp or 0):>7.2f}{cand_txt:>11}")

# max |t| toutes features non-baseline
all_t = []
for tf in tfs:
    for sym in T[tf]:
        for feat in FEATURES:
            if feat == 'geom_vote':
                continue
            node = T[tf][sym].get(feat) or {}
            for h in ('h1', 'h4', 'h24'):
                hn = node.get(h) or {}
                all_t.append(max(abs(hn.get('t_r') or 0), abs(hn.get('t_p') or 0)))
print(f"\n  -> features candidates (|t|>=3): {len(promus)} sur {len(all_t)} (feature×sym×h)")
print(f"  -> |t| max toutes features non-baseline = {max(all_t):.2f}")
if promus:
    print("     " + " ; ".join(f"{f}/{s}/{h} t_r={tr:.1f} t_p={tp:.1f}" for f, s, h, tr, tp in promus[:6]))
print("\nLecture seule. Aucun ordre.")
