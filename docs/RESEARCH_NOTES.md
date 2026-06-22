# RESEARCH NOTES — fondations du « cerveau »

> Notes de lecture **persistées** (survivent à la compaction). Chaque point est
> relié à une décision d'architecture concrète du cerveau (`swarm_brain.py`).
> Objectif : un cerveau **robuste et honnête**, pas un oracle.

## Réponse directe : le cerveau est-il un réseau neuronal ?
**Non.** C'est un **ensemble pondéré d'agents** (mixture-of-experts) avec
**apprentissage en ligne multiplicatif** (famille *Hedge / multiplicative
weights*). Chaque agent vote une direction + une confiance ; le consensus est
une moyenne pondérée ; les poids montent/descendent selon le taux de réussite
passé. Et la recherche dit que **c'est un bon choix** pour ce problème (voir §1).

---

## §1 — Plus profond ≠ mieux (réseaux de neurones)
**Wang 2025, "Better Inputs Matter More Than Stacking Another Hidden Layer"
(arXiv:2506.05764)** — BTC/USDT LOB, 100 ms.
- XGBoost / régression logistique **égalent ou battent** DeepLOB et CNN+LSTM,
  avec une **latence bien moindre**. Précision 0.42–0.71 selon horizon/profondeur.
- Ce qui compte : **qualité des features**, **débruitage** (Savitzky–Golay >
  Kalman ici), **horizon** et **profondeur du carnet** — PAS le nombre de couches.
- Latence = alpha : un modèle 80 % précis qui met 2 s à prédire le prochain 1 s
  est inutile.
- → **Décision** : on garde un ensemble simple et interprétable. Pas de deep net.
  Si un jour on « apprend » plus, viser **régression logistique / gradient
  boosting** sur de bonnes features, pas un réseau profond.

## §2 — Ensembles à pondération adaptative (cœur du cerveau)
**Amega 2025, EARCP (arXiv:2603.14651)** ; **Numin, Weighted-Majority
(arXiv:2412.03167)** ; base théorique Hedge (Freund–Schapire).
- EARCP pondère chaque expert par **performance** (EMA des pertes) **ET
  cohérence** (accord avec les autres) : `s_i = β·P̃_i + (1−β)·C̃_i`, puis
  `w_i ∝ exp(η·s_i)`, **plancher** `w_min` et renormalisation. Regret `O(√(T·logM))`.
- Réglages utiles : `β≈0.7` (favorise la perf), `α_P∈[0.85,0.95]`, `w_min≥0.05`,
  `η∈[3,7]`. **Surveiller l'entropie des poids** `H=−Σ w·log w` (basse = sur-
  concentration).
- **Plancher de poids = exploration** : ne jamais laisser un agent tomber à 0
  (un mauvais agent peut redevenir utile en régime non-stationnaire).
- ⚠️ **Cohérence adverse (« groupthink »)** : si les agents s'accordent sur une
  **erreur**, la cohérence **amplifie** l'erreur. Antidote : diversité (plancher)
  + prudence quand l'accord est trop fort.
- → **Décisions appliquées** :
  1. `update_weights` reste multiplicatif **borné [0.2, 3.0] + normalisé**
     (déjà une variante Hedge avec plancher/plafond). ✓
  2. Ajout d'une **couche méta « cognition »** : entropie des poids, accord
     directionnel, dispersion, **drapeau groupthink**, et **escompte de
     conviction** quand groupthink (prudence anti-cohérence-adverse).
  3. Ajout d'un **agent divergent** (style mean-reversion/contrarian) pour
     **maximiser la diversité** des biais inductifs (EARCP : des experts
     hétérogènes aux erreurs décorrélées améliorent l'ensemble).

## §3 — Microstructure & dérivés (signaux des agents)
**Order-flow** : Cont/Kukanov, et arXiv:2408.03594, 2505.17388, 2112.02947 —
l'**Order-Flow Imbalance** (multi-niveaux) a un pouvoir prédictif court-terme réel
sur les retours. → conforte `agent_orderflow` (imbalance + CVD).
**Funding & contexte 4 h** : arXiv:2601.06084 — les *ranges* émergent du couplage
contexte × conditions de capital ; funding élevé = positionnement chargé. →
conforte `agent_derivs` (funding contrarian) et l'agent **liquidations**.
**Liquidations** : arXiv:2602.12104, 2501.09404 — les cascades de liquidation
créent des zones d'attraction de prix. → conforte la carte de liquidations comme
**aimants de liquidité** (modèle prix×levier×OI).

## §4 — Surapprentissage & honnêteté (backtest)
**Gort et al. 2022 (arXiv:2209.05559)**, De Prado.
- Le **backtest overfitting** est un faux positif courant. Le walk-forward sur un
  seul découpage **surapprend**.
- Outils : **Combinatorial Cross-Validation** + **Probability of Backtest
  Overfitting (PBO)** (logit du rang OOS du meilleur IS) ; rejeter si `p ≥ α`.
- Frais crypto ~0.3 %/trade ; **contrôle du risque** (CVIX : couper l'achat /
  liquider au-dessus d'un seuil de volatilité).
- Même le meilleur agent **perd** pendant les krachs → ne jamais promettre du
  profit.
- → **Décisions** : `backtest_brain.py` inclut **les frais** et compare au
  **buy&hold** (edge honnête). À faire ensuite : **walk-forward / CSCV + PBO**
  pour étiqueter un signal « probablement surappris ».

## §5 — Non-stationnarité (deep RL)
arXiv:2006.05826, 2602.19373, 2512.10913 — la non-stationnarité dégrade les
modèles complexes ; modèles simples + adaptation en ligne + gestion du risque
souvent plus robustes en live. → conforte l'approche ensemble + poids en ligne.

## §6 — Signaux avant-coureurs / ANTICIPATION (agent divergent)
**Scheffer et al., Nature 2009 (early-warning signals)** ; **Guttal & Diks,
PLOS One 2015** ; **« Critical slowing down as EWS for financial crises? »,
Empirical Economics 2019** ; alphaXiv 2604.21297 (dynamical network markers),
2604.20949 (latent microstructure regimes), 2509.04683 (flickering / echoes
before collapse).
- **Critical slowing down (CSD)** : à l'approche d'un point de bascule, un
  système se rétablit **plus lentement** après un choc → la **variance** et
  **l'autocorrélation lag-1** des rendements **montent AVANT** la transition.
  Ce sont des indicateurs **anticipateurs** (leading), pas réactifs.
- ⚠️ **Nuance honnête** : sur les marchés, la preuve est **mixte pour
  l'autocorrélation** (CSD pas toujours présent avant les krachs récents) mais
  **robuste pour la variance montante** (« rising variability »). → on **pondère
  la variance plus fort** que l'autocorrélation (0.5 vs 0.3).
- **Flickering / skewness** : oscillations croissantes entre états avant bascule.
- → **Décision** : `divergent_score` **réécrit**. Ce n'est plus un simple
  contrarien (« voter contre »), mais un **angle différent** au sens propre :
  1. **Anticipation de direction** — divergence prix/momentum (le RSI se
     retourne avant le prix).
  2. **Sensibilité aux stimuli faibles** — extension relative en z-score, **sans
     seuils RSI durs** (on « lève les barrières » des paliers fixes).
  3. **Anticipation d'intensité** — instabilité CSD (variance + autocorr lag-1)
     calculée sur les rendements **bruts** (le débruitage effacerait le signal) :
     quand la résilience chute, l'agent devient **plus convaincu**.

---

## Feuille de route « cerveau » (issue de la recherche)
- [x] Ensemble pondéré + apprentissage en ligne (Hedge borné). 
- [x] **Agent divergent** — réécrit en agent **anticipateur** (divergence
      prix/momentum + critical slowing down sur rendements bruts + sensibilité
      relative sans seuils durs). N'est plus une simple opposition (§6).
- [x] **Couche cognition** — entropie, accord, dispersion, drapeau groupthink,
      escompte de conviction (anti-cohérence-adverse).
- [ ] Pondération EARCP complète (perf **+** cohérence explicite avec `β`, `η`,
      `w_min`) — évolution possible de `update_weights`.
- [x] **PBO / CSCV + walk-forward** dans `backtest_brain.py` (garde-fou anti-
      surapprentissage ; sur BTC 1H le signal technique seul sort PBO≈0.46 et
      0/5 tranches gagnantes → confirmé non déployable, honnêtement).
- [x] Débruitage **Savitzky–Golay** des clôtures avant indicateurs (§1), dans
      `technical_signal` et `divergent_score`. Mesure honnête BTC 1H : Sharpe
      −0.31→+0.12, edge −6.0%→−1.8%, DD −8.4%→−6.5%, tranches gagnantes 0%→40% ;
      MAIS PBO reste élevé (~0.77) → meilleures features, edge encore non robuste.
- [ ] Si « plus d'apprentissage » : régression logistique / gradient boosting sur
      bonnes features (jamais un deep net en premier — §1).

_Références : 2506.05764, 2603.14651, 2412.03167, 2408.03594, 2505.17388,
2112.02947, 2601.06084, 2602.12104, 2501.09404, 2209.05559, 2006.05826,
2604.21297, 2604.20949, 2509.04683 ; Scheffer Nature 2009 ; Guttal/Diks PLOS
One 2015 ; Empirical Economics 57(4) 2019._
