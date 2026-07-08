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

- **CPCV (Combinatorial Purged CV) — n°1, PROUVÉ FAISABLE SANS DÉPENDANCE.** Précision post-vérif :
  `agent_validation.py` a DÉJÀ le Deflated Sharpe (`deflated_sharpe`), le PSR et les rendements
  purgés (`purged_forward_returns`) — mais en walk-forward MONO-chemin. Le vrai gap = la CPCV
  MULTI-chemins de López de Prado : au lieu d'UN train/test, tester C(N,k) combinaisons de groupes
  (purge+embargo) → une DISTRIBUTION d'IC OOS, pas un point. Un edge fragile s'effondre sur la
  dispersion. **DÉMONTRÉ en numpy pur (scratchpad/geometric_v2_lab/cpcv_demo.py, AUCUN install) sur
  w1_drift/XRP-1H-h4** : le WF simple « validait » un incrément +0.047 ; la CPCV (45 chemins) révèle
  p10 = −0.000 (l'apport s'annule sur ~11 % des chemins) → fragile. C'est exactement la sur-détection
  d'overfitting recherchée. → À PORTER dans `agent_validation` comme check de promotion DURCI
  (~60 lignes numpy, zéro dépendance, strictement plus de rigueur, ne touche PAS guards()). Passe
  par les 3 portes. `skfolio` (BSD) l'automatise mais N'EST PAS nécessaire (remplaçant de `mlfinlab`
  devenu propriétaire — utile seulement pour HRP/risk-parity du sizing `mandate`, secondaire).
- **`finance_ml`** (port MIT de López de Prado, figé 2020 → PORTER les fonctions, ne pas
  `pip install`) : poids d'unicité, **fractional differentiation** (stationnarité en gardant la
  mémoire), meta-labeling → `agent_validation`.
- **MCPT / Taguchi / données synthétiques** (BuildAlpha) : Monte-Carlo par permutation + designs
  de robustesse pour durcir la barre « le signal survit-il au hasard ? ». Sert le §68.
- Cross-cutting : **le survivorship-bias dataset** (univers historique complet listing/delisting)
  pour que les rejeux 6 ans ne soient pas biaisés (à confirmer par le sous-agent validation).

## PRIORITÉ 2 — la porte de RÉGIME ⚠️ THÈSE MESURÉE et RÉFUTÉE (démotée)

BuildAlpha (200-SMA), BlackBull (multi-TF, squeeze), MQL5, LuxAlgo pointent tous vers le même
principe : **conditionner le signal par le régime.** Cette « sagesse convergente » a été TESTÉE
deux fois et **ne survit PAS à la mesure rigoureuse dans les données de ce bot** :
- **Gate-VOLATILITÉ** (§103, tâche 1 geometric) : gater le momentum par le régime de vol/dérive
  n'ajoute aucun edge robuste (séparation d'IC nulle).
- **Gate-EFFICIENCE de tendance KER** (kaufman_gate.py, mesuré CPCV/WF purgé) : REJETÉ. 4/24
  cellules |t_diff|≥3, toutes 5m/15m, s'évanouit à 1H/4H (pas cohérent cross-TF), et surtout
  **signe INVERSÉ** — quand l'efficience de tendance est haute, le momentum devient PLUS réversif,
  pas plus tendanciel (fait stylisé crypto §35-38 retrouvé). L'hypothèse « le momentum marche
  mieux en tendance efficiente » est FAUSSE ici.
**Conclusion : gater le signal directionnel par le régime = piste plausible mais non prouvée,
rejetée sur deux régresseurs de gate indépendants.** Ne pas brancher. Résultat négatif de valeur
(évite un gate séduisant mais faux). Reste théoriquement ouvert : gater le SIZING (pas la
direction) par le régime de vol — mais c'est déjà ce que fait le vol-targeting GARCH de `mandate`.
Les items ci-dessous sont donc DÉMOTÉS (mesure d'abord requise, prior défavorable) :

- **Gate KER (Kaufman Efficiency Ratio)** : efficience de tendance (trend vs chop) → module la
  confiance des voix momentum. **Distinct du gate-vol réfuté §103** (gate sur la persistance
  directionnelle, pas la vol). Bon marché, non testé. → la piste-gate n°1.
- **Porte 200-SMA** (n'agir que du bon côté de la tendance longue), **porte multi-TF** (un TF
  supérieur en barres CLÔTURÉES autorise/bloque le TF d'exécution), **squeeze de Bollinger
  BandWidth** (compression bas-percentile → expansion) comme CONDITIONNEURS. → overlays §106 /
  `mandate.py`.
- Protocole gate : mesurer si le gate CONCENTRE l'edge d'une voix qui a DÉJÀ de l'edge (pas
  fabriquer de l'edge sur du bruit — leçon §103) ; valeur économique (Sharpe) requise.

## PRIORITÉ 2bis — SOURCES DE DONNÉES ALPHA HORS-OHLCV (élargir l'information, pas transformer le prix)

Salve on-chain/dérivés/sentiment/macro (08/07). Plus haute valeur potentielle que P3 : c'est de
la NOUVELLE information, pas un énième transform du prix. Le bot a déjà funding 8 h
(`funding_history`), FEAR_GREED, qualité CoinGecko, `funding_fade` §75, black-out Kalshi §59.
⚠️ Caveats TRANSVERSES : (a) **ERR-003** — re-confirmer chaque endpoint contre l'API live avant
intégration ; (b) **fréquence native ≠ TF de test** — funding 8 h, flux/F&G/macro journaliers →
tester aux TF ≥ fréquence native seulement (sinon valeur stale répétée = IC gonflé) ; (c) **ERR-007**
— étiquetage d'adresses on-chain RÉVISÉ a posteriori = look-ahead : verrouiller la date d'observation ;
(d) jamais desserrer `guards()` — ces signaux sont des GATES/voix opt-in §72, pas des murs.

Ordre suggéré (gratuit + causal + testable) :
1. **Skew d'options 25Δ + DVOL (Deribit, API publique SANS auth)** — NOUVEL AXE (options), absent du
   bot. `RR25 = IV(put25Δ)−IV(call25Δ)` + DVOL (VIX crypto, depuis 2021, 1 min). Contrarien
   (RR25 très négatif = peur → forward +) ET gate vol-targeting (`mandate.py`). Couverture BTC/ETH(+SOL)
   seulement → alts = NaN (ne pas fabriquer). Deribit ≠ flux Bitget (proxy).
2. **Base perp-spot annualisée (Bitget public + spot CoinGecko)** — `basis=(mark−index)/index`,
   LATENCE NULLE (pas d'attente settlement), continue (~1 min, tous TF). Mean-rev : base très
   positive → forward −. Gate « euphorie de levier » ou voix §72 si incrément au funding. Quasi-
   fonction du funding cumulé → tester l'incrément.
3. **Flux d'OI = sign(ΔP)·ΔlnOI (Bitget public snapshot, À LOGGER — pas d'historique gratuit)** —
   momentum si OI monte avec le prix ; rebond sur collapse d'OI (capitulation). Voix §72 + gate
   « deleveraging ». Cold-start (historique dès branchement) ; wash-trading gonfle l'OI.
4. **Net-inflow USDT vers exchanges (Coin Metrics Community API, gratuit, sans clé)** — le mieux
   étayé (arXiv 2411.06327 : USDT netflow prédit BTC/ETH à 1-6 h ; netflow ETH prédit NÉGATIVEMENT
   ETH). + SSR = mcap(BTC)/mcap(stables) comme gate lent. Gratuit = journalier (D1/W1 propres) ;
   l'edge 1-6 h exige le flux horaire (payant) — reproduire en D1 gratuit d'abord.
5. **Pente de structure de terme du funding** — `z=(funding−médiane90j)/MAD90j` + pente vs EWMA.
   Contrarien, enrichit `funding_fade` §75 (test d'incrémentalité). Native 8 h → edge propre ≥ H4.
6. **F&G + ratio long/short en gate contrarien** (alternative.me + Bitget long-short) — ⚠️ CIRCULARITÉ :
   le F&G intègre déjà vol+momentum de prix → fuite depuis l'OHLCV, mesurer l'incrément NET. Gate lent.
7. **Gate macro risk-off (FRED clé gratuite / Alpha Vantage / Stooq — PAS investing.com)** —
   `risk_off_z` = z composite {ΔDXY(FRED DTWEXBGS), ΔDGS2, ΔVIXCLS} (+ or/BTC). Gate lent D1/W1,
   complète §59. ⚠️ investing.com = Cloudflare/anti-bot → NE PAS tenter sur le VPS (précédent
   TradingView headless abandonné 06/07). ⚠️ ERR-003 : dans le MCP Alpha Vantage, `DX` = Directional
   Movement Index, PAS le dollar index (utiliser FRED DTWEXBGS ou proxy EUR/USD). Désync crypto 24/7
   vs TradFi fermé nuit/WE → forward-fill = look-ahead si mal fait ; signal LENT (faible pour un
   cerveau 1 min).

## PRIORITÉ 3 — signaux candidats voix §72 (chacun opt-in, marginal-vs-existant)

⚠️ MESURÉ (SuperTrend/Vortex/CMF, WF purgé sur 6 ans) : en TIME-SERIES ils ont un IC directionnel
NÉGATIF court terme (|IC|~0.03, t jusqu'à −10), identique à un contrôle `mom` (rendement brut) →
c'est la **réversion crypto canonique §35-38 mesurée 4 fois** (signaux colinéaires « le prix vient
de monter »), PAS 3 signaux indépendants. Reformulé : « fader » ces signaux a un IC +0.03 cohérent
— mais c'est **très probablement REDONDANT avec le cœur réversion existant** du bot (à prouver par
orthogonalisation + net de frais avant toute valeur ; prior = redondant, pas d'alpha neuf). LE
momentum POSITIF en crypto n'est pas là : il vit en **CROSS-SECTIONAL** (rang entre coins,
Liu-Tsyvinski-Wu) et à horizon long, pas en time-series court → **piste #8 à ÉLEVER** (facteur
momentum cross-sectionnel, axe distinct du bot actuel). Leçon : tester chaque signal sur l'axe/
horizon où il est conçu pour payer, pas contre le rendement signé court où la réversion écrase tout.

- **Momentum CROSS-SECTIONAL (#8, Liu-Tsyvinski-Wu)** — ÉLEVÉ : rang de performance entre coins de
  l'univers (pas time-series). Le vrai gisement de momentum positif crypto. Voix/tilt §72, à mesurer
  en priorité parmi les signaux (nécessite l'univers multi-coins, pas juste BTC/ETH).
- **SuperTrend** (trailing ATR) — comme **trailing-stop / sizing** (distance à la bande), pas un
  vote directionnel (son IC time-series = réversion redondante, cf. ci-dessus).
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

## PRIORITÉ 3bis — FUSION NEURONALE (16ᵉ voix `neural_net.py`) + QML (18ᵉ)

Salve NN/QML (08/07), toutes CPU/dépendance-légère (torch/sklearn déjà là), benchmark dur =
la **cible ridge §78** (une technique qui ne la bat pas en IC OOS purgé = ne pas armer).
Ordre d'attaque : **FUS-02 d'abord** (l'instrument de mesure honnête), puis le reste — sinon
les gains sont des mirages de régime ([[measurement-blind-spot]]).

- **FUS-02 [VALID] — purged K-fold + embargo + CPCV + MDA POUR le NN.** Converge avec le n°1
  (P1) : mêmes plis CPCV que le NN pour comparer voix à voix ; MDA (permutation d'un vote →
  chute d'IC OOS) sous CV purgée pour classer les 14 votes réellement exploités. Prérequis à
  tout le reste. sklearn déjà là.
- **FUS-03 [ARCHI] — régularisation, coût CPU nul, la plus prête** : AdamW (weight decay
  découplé) + Dropout(0.2–0.5) + early-stopping sur l'IC du pli PURGÉ (pas la loss de train).
  → `neural_net.py`, zéro dépendance.
- **FUS-01 [ARCHI] — meta-labeling + poids d'unicité** (López de Prado) : le NN devient méta-modèle
  (cible = « le banc a-t-il eu raison ? » → module la TAILLE, pas la direction), échantillons
  pondérés unicité×|rendement|. Cohérent « déterministe d'abord ». À mesurer sur 6 ans (rare/
  déséquilibré → mémorise le régime en petit échantillon).
- **FUS-04 [ARCHI post-hoc] — calibration** : température (déjà §73) → Platt/isotonic sur plis OOS
  purgés (sizing = proba fiable). Isotonic sur-apprend en petit N → rester température tant que N bas.
- **FUS-05 [ARCHI] — ensembles bon marché** : SWA (`torch.optim.swa_utils`, quasi gratuit à
  l'inférence CPU) + snapshot ensembles ; réduit la variance inter-plis, pas le biais.
- **QML-01 [ARCHI, LABO seulement] — durcir le circuit §100** (venv isolé, ERR-004) : data
  re-uploading (expressivité à 6 qubits sans empiler de portes), **budget de portes borné**
  (généralisation ~√(T/N) → LIMITER T = contrôle direct du sur-apprentissage), anti-barren-plateaus
  (init blocs-identité, profondeur modeste). Ajouter des portes aggrave à la fois sur-apprentissage
  ET barren plateau ET le rejeu numpy prod. Voix reste muette par porte d'edge.
- **QML-02 [VERDICT] — hardware quantique réel (IBM/OpenQuantum/…) = RIEN de mesurable au stade
  NISQ.** Un seul verdict tous fournisseurs : files cloud minutes-heures (rédhibitoire pour un vote
  1 min), bruit NISQ, zéro avantage quantique reproductible en ML financier ; tout circuit à erreur
  mitigeable est classiquement simulable. **La simu numpy-pure §100 est le BON choix.** Ne rien
  brancher tant que qml_shadow ne bat pas le ridge §78 en WF purgé sur 6 ans + edge>0 après porte
  prudente sur plusieurs plis CPCV. NB : le « seul chantier légitime » cité (poser le cron de
  réentraînement §100) est **DÉJÀ FAIT** (posé cette session, dim 04:40) — reste à laisser l'ombre
  mesurer. Si un jour l'edge classique est prouvé, l'accès hardware passe par `pennylane-qiskit`
  en venv isolé — jamais un 2ᵉ SDK.

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
