# smc_execution_lab.py — mesure d'EXÉCUTION du SMC (la bonne lentille, ERR-016)

## Pourquoi (le reframe propriétaire)

Le propriétaire a corrigé une erreur de méthode (ERR-016) : **SMC n'est pas un prédicteur
directionnel — c'est une reconnaissance de structure qui dit OÙ on est dans le mouvement pour bien
PLACER ses ordres.** Le mesurer à l'IC directionnelle (fait, ≈0) répondait à la mauvaise question.
La BONNE question, sur le SEUL levier réel du bot (exécution/frais, cf. `docs/…` mémoire
`exec-fees-lever`) : **un fill MAKER posé à un niveau de structure SMC a-t-il un meilleur MARKOUT
(moins de sélection adverse) qu'un fill maker naïf ?**

## Méthode (mirror de `vpin_lab`, contexte = structure SMC)

Classé **SAFE** (`security_agent.FILES_TO_SCAN`), LECTURE SEULE, PUR, AUCUN ordre, défaut OFF.
- **Fills maker post-only** simulés comme dans `vpin_lab` : fair = close précédente ; bid/ask =
  fair·(1∓spread/2) ; buy rempli si low≤bid, sell si high≥ask (borne sup sans file d'attente).
- **Markout net** `h` barres plus tard : `microstructure.markout(price, side, future_mid)` réutilisé
  tel quel, moins les frais maker (2 bps/fill). `future_mid` ≈ close_{i+h} (pas de carnet L1
  historique — même proxy que vpin_lab).
- **Tag SMC causal** de chaque fill : la zone (FVG/BPR/niveau balayé) est établie ≤ i−2 (délai
  fractal smc) et « active » (FVG/BPR ~40 barres, sweep ~30). Le fill est `at_structure` s'il tombe
  dans une zone du **bon côté** (buy dans un FVG haussier / sur un swept-low = support/discount ;
  sell dans un FVG baissier / sur un swept-high = résistance/premium).
- **Expérience** : markout net moyen des fills `at_structure` vs hors-structure. `delta = à-la-
  structure − naïf`. Welch t + bootstrap (diff) + non-chevauchant + **Deflated Sharpe** déflaté par
  N_trials = sym×TF×h = 192. Échelle TF complète M1..W1 (ERR-001).
- **Perf** : les zones (h-indépendantes) sont calculées 1×/cellule et indexées par barre de création
  → seules les zones ACTIVES à chaque fill sont testées (sinon O(n_fills×n_zones), ~7000 sweeps).

## Verdict (19/07) — SMC N'AMÉLIORE PAS l'exécution, prior tenu

`--run-all` (8 majors × M1..W1 × h{3,6,12}) : **0 essai robuste, non cohérent 2 TF.**
- Le « meilleur » delta (BTC 1W h=12 : +2000 bps, t=3,66) est un **artefact small-n haute-TF**
  (n_at=43, markout sur 12 semaines dominé par la tendance) — **tué par DSR=0,58<0,95**. Tous les
  gros deltas positifs sont 1D/1W à n<60 (même piège que `chart_patterns`/`wyckoff_lab`).
- Là où l'échantillon est FIABLE (intraday, grand n), l'effet est **≈0 voire NÉGATIF** : BTC 1H
  delta **−5 à −7 bps** (t~−1,7) = **sélection adverse** — les FVG et niveaux balayés sont
  précisément la liquidité qui se fait courir (*fill-and-be-run*), cohérent avec la microstructure
  du stop-hunt.

**Conclusion** : mesuré à la BONNE lentille (markout/exécution, pas l'IC directionnelle), SMC
n'ajoute pas de valeur — ce n'était donc pas un problème de lentille, l'edge n'y est simplement pas.
Le levier exécution reste réel (le maker sur les ouvertures = seul gain net observé du dépôt), mais
la structure SMC ne le capte pas ; elle marque plutôt des zones de fill TOXIQUE. Ne rien brancher.

## Usage

```bash
python smc_execution_lab.py --status
python smc_execution_lab.py --run BTCUSDT 1H     # markout structure vs naïf par horizon
python smc_execution_lab.py --run-all            # univers × TF × horizons + verdict déflaté
```

Artefact : `.smc_execution_lab_result.jsonl` (gitignoré via `*.jsonl`).
