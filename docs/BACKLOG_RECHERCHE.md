# BACKLOG_RECHERCHE.md — pistes testables issues de la campagne de recherche (§104)

**Origine.** Campagne de recherche bot-large (08/07/2026, décision propriétaire « assumer la
campagne ») : dépouillement de sources externes (BuildAlpha, MQL5, BlackBull, TradingView,
LuxAlgo, GitHub MetaTrader, écosystème quant Python) par une arborescence de sous-agents.

**STATUT DE TOUT CE FICHIER : PISTES NON VÉRIFIÉES.** Rien ici n'est mesuré ni branché. Chaque
piste suit la même discipline avant tout usage :
- opt-in au **labo §72** (jamais le banc déterministe GELÉ à 14, §62) ;
- testée sur l'**échelle COMPLÈTE M1..W1** (ERR-001), IC rang ET pearson, t par pli en
  walk-forward PURGÉ, barre |t|≥3 cohérent plis+TFs ;
- jugée en **apport MARGINAL** vs l'existant (colinéarité), pas en IC brut ;
- **contrôle anti-repaint** obligatoire pour tout indicateur à pivots/ZigZag/régression
  récursive/noyau symétrique (réécrire en endpoint one-sided ou REJETER) ;
- dépendance tierce → **venv isolé** + `pip install --dry-run` (ERR-004), et **licence lue en
  clair** (le badge GitHub ment souvent `NOASSERTION`) : ne vendoriser QUE MIT/BSD/Apache ;
- **jamais** un desserrage de `guards()` (murs 50/250, ×5, stop −5 %, kill-switch).

---

## PRIORITÉ 1 — durcir le JUGE (sert TOUTES les voix, meilleur ROI)

Améliorer la porte de promotion §68 / `agent_validation` rapporte plus qu'une voix de plus :
c'est le filtre qui décide de n'importe quelle voix.

- **`skfolio`** (BSD-3, bâti sur scikit-learn DÉJÀ installé — friction quasi nulle). Fournit
  clés en main **`CombinatorialPurgedCV` + Deflated Sharpe** (CV purgée combinatoire plus robuste
  que le walk-forward simple actuel) et **HRP / risk-parity** (sizing du book 3 symboles dans
  `mandate`). C'est le **remplaçant open et propre de `mlfinlab` devenu PROPRIÉTAIRE** (à ne
  surtout pas prendre en dépendance). → n°1 à évaluer.
- **`finance_ml`** (port MIT de López de Prado, figé 2020 → PORTER les fonctions, ne pas
  `pip install`) : poids d'unicité, **fractional differentiation** (stationnarité en gardant la
  mémoire), meta-labeling → `agent_validation`.
- **MCPT / Taguchi / données synthétiques** (BuildAlpha) : Monte-Carlo par permutation + designs
  de robustesse pour durcir la barre « le signal survit-il au hasard ? ». Sert le §68.
- Cross-cutting : **le survivorship-bias dataset** (univers historique complet listing/delisting)
  pour que les rejeux 6 ans ne soient pas biaisés (à confirmer par le sous-agent validation).

## PRIORITÉ 2 — la porte de RÉGIME (le thème convergent de TOUTES les sources)

BuildAlpha (200-SMA), BlackBull (multi-TF, squeeze), MQL5, LuxAlgo pointent tous vers le même
principe : **ne pas chercher un meilleur indicateur directionnel, CONDITIONNER le signal par le
régime.** Et le labo geometric (§103) a montré que gater sur la VOLATILITÉ ne sert à rien —
mais ces gates portent sur une variable DIFFÉRENTE (persistance/efficience de tendance).

- **Gate KER (Kaufman Efficiency Ratio)** : efficience de tendance (trend vs chop) → module la
  confiance des voix momentum. **Distinct du gate-vol réfuté §103** (gate sur la persistance
  directionnelle, pas la vol). Bon marché, non testé. → la piste-gate n°1.
- **Porte 200-SMA** (n'agir que du bon côté de la tendance longue), **porte multi-TF** (un TF
  supérieur en barres CLÔTURÉES autorise/bloque le TF d'exécution), **squeeze de Bollinger
  BandWidth** (compression bas-percentile → expansion) comme CONDITIONNEURS. → overlays §106 /
  `mandate.py`.
- Protocole gate : mesurer si le gate CONCENTRE l'edge d'une voix qui a DÉJÀ de l'edge (pas
  fabriquer de l'edge sur du bruit — leçon §103) ; valeur économique (Sharpe) requise.

## PRIORITÉ 3 — signaux candidats voix §72 (chacun opt-in, marginal-vs-existant)

- **SuperTrend** (trailing ATR, bascule de régime) — surtout comme **trailing-stop / sizing**
  (distance à la bande = dimensionnement), pas juste un vote.
- **Ultimate RSI** [LuxAlgo] (RSI reconçu pour la tendance via rolling range) — momentum, à
  décorréler de RSI/MACD. Meurt en range → à coupler au gate KER.
- **Predictive Ranges** [LuxAlgo] (niveau central ATR à crémaillère + bandes) — mean-rev/niveaux
  S-R. ⚠️ **replay anti-repaint OBLIGATOIRE** avant tout (étiquette « do not repaint » non fiable).
- **Vortex VI+/VI−**, **Fisher Transform** (sur barre confirmée), **Chaikin Money Flow** —
  candidats à décorréler d'ADX/VWAP/Bollinger existants.
- **funding/OI comme indice « COT »** → `funding_fade` §75. **Ratio alt/BTC retardé** → volet
  `pairs` §82. **Kalman hedge-ratio dynamique** (letianzj) → jambes carry/pairs §82.
- Méthodo : **sélection de paramètre adaptative par k-means** (SuperTrend AI) — régler une voix
  en ligne au lieu de figer un paramètre ; à ne tenter qu'APRÈS avoir prouvé la voix de base.
- Réservoirs d'indicateurs à miner (MIT, pandas pur, zéro risque de pile) : **`bukosabino/ta`**
  (Vortex, Force Index, KST…), catalogue Alpha158/360 de **qlib** (transcrire, pas dépendre).

## PRIORITÉ 4 — sous-systèmes spécifiques (si/quand on les travaille)

- **Market making §94** : extraire les formules **Avellaneda-Stoikov** de **hummingbot** (Apache
  — prendre la MATH, pas le framework d'exécution) : skew d'inventaire, adverse-selection.
  (Salve MM du sous-agent encore en vol — à compléter.)
- **Features macro/cross-asset** : route pour aspirer DXY/or/indices/forex en pandas — via les
  MCP déjà branchés (alphavantage/coinpaprika/market-data) de préférence, ou `ejtraderMT`
  (GPL → ré-implémenter) depuis Linux contre un terminal wine si besoin.
- **Cribleur rapide** : **`vectorbt`** (venv isolé, Commons Clause = usage interne OK) pour
  balayer des milliers de combos M1..W1 en secondes et PRÉ-filtrer avant la validation maison
  rigoureuse (ne REMPLACE pas `agent_validation` — pas de forward purgé).

## ÉCARTÉS (nommés, pour ne pas les re-tester)

- **SMC / Order-Blocks / FVG / Liquidity / Market-Structure / ICT / Nadaraya-Watson brut** :
  repaint (pivots/ZigZag/noyau symétrique) ET déjà mesurés net-négatifs (§80, [[smc-aio-rejected]]).
  ~80-90 % des catalogues « trending »/LuxAlgo tombent ici ou en premium closed-source.
- **martingale / grid-sans-stop / averaging-down / news-straddle** : profils de RISQUE, pas des
  edges — incompatibles avec les murs durs ; le black-out macro §59 couvre déjà les news.
- **Frameworks d'EXÉCUTION** (blankly, freqtrade, Auto-GPT-MT, metaapi, hummingbot-framework) :
  dupliquent le bridge/backtest maison (souvent moins rigoureux) ET passent des ordres (hors
  mandat lecture seule). Lecture d'idées uniquement. **Conlan** duplique `agent_validation` en
  moins rigoureux (réf de style, pas d'intégration).
- **Licences à bannir en dépendance** : `mlfinlab` (propriétaire), `freqtrade` (GPL virale),
  `vectorbt` (Commons Clause → venv isolé, pas de revente), `blankly` (LGPL), Conlan (freeware).

---

*Salves encore en vol au moment de l'écriture (à intégrer) : Market-making, Validation/robustesse,
On-chain/dérivés, NN/QML. Le fichier est un backlog VIVANT — les mesures qui valideront ou
réfuteront une piste vont dans `RESEARCH_NOTES.md`, pas ici.*
