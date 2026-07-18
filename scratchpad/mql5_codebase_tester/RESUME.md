# REPRISE — pipeline mql5.com (arrêt raisonné le 09/07/2026)

## Où on s'est arrêté
- **Catalogue + triage** : COMPLET (103 articles uniques, `catalog.json` / `queue.json`).
- **Testés** : 2 candidats, tous **REJETÉS** (`verdicts.jsonl`) —
  `kalman_slope` 0/34, `struct_break_suite` (AFML Ch.17) 0/40.
- **Arrêt décidé** : 2/2 rejets + verdict de corpus (« recoupe l'existant ») + le vrai
  levier est l'exécution/frais ([[exec-fees-lever]]). Le coût de reprise est en TOKENS
  (réimplémenter chaque candidat), PAS en compute (un test = ~15 s de CPU, ~0 token).

## Shortlist ciblée pour reprendre — `resume_shortlist.json` (45 items)
58 items écartés sans test (Wizard NN/LSTM/GRU redondants avec nos voix nn/qml, infra MT5,
accessibilité/BCI, topologie déjà réfutée, money-management/trailing hors signal). Les seuls
à VRAI signal nouveau (haut de shortlist) :
- `Divergence System: MPO4 Custom Indicator` (score 5)
- `Low-Frequency Quant (Part 4): Volatility-Aware strategy` (score 4)
- `Meta-Labeling the Classics (Part 2): ADX` (score 4 — c'est du SIZING/filtre, pas un signal brut)
- `Forecasting Using Grey Models` (score 2)
- `Graph Theory: Network Flow (Ford-Fulkerson) as indicator` (score 2)

## Méthode de reprise LA MOINS CHÈRE (à suivre plus tard)
1. **Déléguer à un sous-agent** (`general-purpose` ou fork) : lui passer 3-5 items de la
   shortlist, il réimplémente dans `candidates.py`, lance `run_candidate.py <nom>` et
   renvoie SEULEMENT une ligne de verdict par candidat. → les tokens de réimplémentation
   restent HORS du contexte principal ; je ne récupère que le résumé compact.
2. **Par lots** : réimplémenter plusieurs candidats puis 1 seul run/rapport (amortir le report).
3. **Prior honnête** : attendre surtout des rejets (§104 — les signaux simples < frais).
   Un survivant net-de-frais (porte §77 t≥3) serait la vraie surprise à remonter.

Reprise = « teste les N prochains de `resume_shortlist.json` via un sous-agent ».
