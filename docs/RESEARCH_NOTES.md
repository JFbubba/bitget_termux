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

## §7 — Sources de données & dépendance externe au runtime
Revue de 13 ressources (CCXT, yfinance, QuantInsti, LuxAlgo, TradingView,
ChartingLens, Tickeron, MQL5, FXReplay, TradeStation-alts, TDLib, arXiv, Reddit).
- **Sources branchables, gratuites, programmables** :
  - **Bitget REST** (déjà utilisé, joignable au runtime — vérifié) : OHLCV, carnet,
    funding, OI. **Source primaire fiable.**
  - **CCXT** (installé) : API unifiée 100+ exchanges, Bitget inclus, **données
    publiques sans clé**, websockets via CCXT Pro. → repli/unification possible.
    ⚠️ **Réalité réseau constatée ici** : Binance (451) et OKX (403) **géo-bloqués**
    → la valeur multi-exchange de CCXT ne s'applique pas dans cet environnement ;
    réservé à un déploiement à réseau complet.
  - **CoinGecko** (joignable, gratuit, hôte indépendant) : vraie **redondance**
    de prix face à Bitget. → branché comme **repli** dans `market_sources.py`.
  - **yfinance** (installé) : macro gratuite (SPX/DXY/VIX/or) mais **non officielle,
    rate-limitée, usage perso** (endpoint Yahoo a renvoyé HTTPError ici) → à mettre
    **derrière cache + repli**, jamais sur le chemin critique.
  - **MCP CoinDesk** (funding/OI/carnet/news) et **MCP Bigdata.com** (sentiment) :
    enrichissement, mais dépendance externe au runtime → cache + dégradation.
  - **TDLib** : ingestion de canaux Telegram (news/signaux) en lecture, bindings
    Python — mais **compilation lourde** (OpenSSL/zlib) → différé.
- **Non branchables** : Tickeron, ChartingLens, FXReplay, MT5/MQL5, TradeStation —
  **web/manuel, pas d'API gratuite** ; MQL5 confirme néanmoins nos garde-fous de
  risque (sizing, breakeven, trailing) comme standards. À noter honnêtement.
- **Bibliothèques (décisions, recheck confirmé)** : on reste sur nos indicateurs
  **purs** (vs TA-Lib/pandas-ta) et notre backtest (vs backtrader/vectorbt/zipline)
  pour l'auditabilité ; si « plus d'apprentissage » : **scikit-learn** (gradient
  boosting / logreg), **statsmodels** (ARIMA, validation), jamais un deep net (§1).
  Macro déjà couverte par **FRED** (≈ pandas-datareader) ; **Alpha Vantage** noté
  comme repli optionnel mais **non branché** (éviter la prolifération de clés/
  dépendances — cohérent avec « optimiser la dépendance runtime »). Dashboard :
  **TradingView Lightweight Charts** (Apache-2.0 v4.2.3, auto-hébergé) **déjà
  intégré** (chandelier + EMA20/EMA50/VWAP/volume, crosshair, toggles) puis
  **enrichi** : bougies via `market_sources` (Bitget→CoinGecko, cachées) + un
  **marqueur de « conscience »** sur la dernière bougie (biais + consensus + régime
  de vol du cerveau).
- **Outils IA web (Tickeron, ChartingLens ×9, FXReplay) — recheck** : **aucune API
  développeur gratuite** confirmée → non branchables (rejet documenté, honnête).
- **Optimiser la dépendance externe au runtime** → `runtime_cache.py` :
  1. **cache TTL** par source (book 10 s, liq 2 min, derivs 5 min, F&G 15 min,
     macro 30 min) — dans le TTL, **zéro appel réseau** ;
  2. **stale-while-error** : sur échec de rafraîchissement, on sert la **dernière
     valeur connue** ; aucune valeur → **fallback neutre** ;
  3. le cerveau ne **bloque jamais** sur une source morte ; latence de décision
     **découplée** de la latence réseau (§1, « latency = alpha ») ;
  4. priorité au **local fiable** (Bitget) sur le chemin chaud ; yfinance/MCP/
     Telegram = enrichissement qui peut échouer en silence.

## §8 — Black-Scholes : la volatilité comme objet central
**Black & Scholes (1973), Merton (1973).** EDP : `∂V/∂t + ½σ²S²·∂²V/∂S² +
rS·∂V/∂S − rV = 0` ; forme fermée `C = S·N(d1) − K·e^{−rT}·N(d2)`.
- On ne trade **pas** d'options ici — mais BS formalise **la** quantité qui
  compte : la **volatilité σ** (seule inconnue). On en tire deux outils
  directement utiles à un bot directionnel, dans `black_scholes.py` (pur, testé
  contre des valeurs connues : call ATM = 7.9656, parité call-put, greeks) :
  1. **N(d2) = P(S_T > K)** (lognormal) → **probabilité d'atteindre un niveau**.
     `prob_touch` (réflexion, drift nul) estime la « force d'aimantation » vers un
     cluster de liquidation.
  2. **Mouvement attendu ≈ S·σ·√T** → **bandes ±1σ** (cône de volatilité) =
     exactement les **bandes de régime CVIX**, avec une largeur fondée.
- → **Décisions appliquées** (dashboard) : projection Black-Scholes côté serveur
  (`_projection`) ; sur le graphique : **bandes ±1σ** colorées par régime CVIX,
  **aimants de liquidation** annotés de leur **probabilité d'atteinte**, et
  **multi-timeframe** (5m/15m/1h — la bande s'élargit en √T, vérifié : ±0.53 %
  → ±1.88 %). **Delta directionnel** dans le panneau cerveau : `P(↑)=N(d2|K=S)`
  / `P(↓)` à l'horizon — légèrement < 50 % par *volatility drag* (dérive −σ²/2),
  d'autant plus marqué que σ√T est grand (honnête). La 3ᵉ image (écosystème
  *trade surveillance*) n'est pas une équation : c'est la couche risque/
  compliance, dont notre analogue est `security_agent` + `risk_manager`.

## §9 — Intake Drive `package/PDF` (papiers analysés)
Lecture de 4 PDF du dossier **`package/PDF`** (périmètre strict : `package` only).
- **Order-flow entropy — « Hidden Order in Trades » (arXiv 2512.15720)** ⭐ 5/5.
  L'entropie de la matrice de transition d'order-flow (15 états = signe ΔP ×
  quintile de volume, fenêtre 120 s) prédit la **MAGNITUDE** des moves, **pas la
  direction** (invariance par permutation de signe). Basse entropie -> gros move
  imminent. → **implémenté** `regime_features.orderflow_entropy()` ; futur **agent
  de gating-magnitude** distinct des agents directionnels (module taille/timing).
  Placebos à ajouter à notre batterie : permutation des labels, scrambling
  temporel, random-entry, correction Bonferroni.
- **Forecast-to-Fill (arXiv 2511.08571)** 4/5 — or, pas crypto, chiffres suspects
  (Sharpe 2.88 incohérent en interne), MAIS squelette d'ingénierie réutilisable :
  mapping **pente standardisée -> proba [0,1]** (`regime_features.slope_to_prob()`),
  blend convexe `0.6·trend + 0.4·momentum`, vol-targeting EWMA capé, et surtout un
  **protocole de validation** qui complète notre PBO : **test SPA/Reality-Check
  (White-Hansen)** sur grille de configs, **placebo par inversion du signal**,
  stress latence T+1/T+2 et coûts 0.5×–2×, gel des paramètres.
- **Drift-regime factor (arXiv 2511.12490 ; fichier « 13-Sharpe »)** 3/5 — actions
  cross-section (≠ notre crypto directionnel), Sharpe 13 invraisemblable (biais de
  survie admis). Techniques extraites : **régime-gating binaire** (activer/désactiver
  un agent selon le régime, pas seulement le pondérer) ; **UpFraction** (fraction de
  jours positifs sur 63) -> `regime_features.up_fraction()` ; **kill-switch
  multi-trigger** (drawdown abs −30 %, rolling-63j −10 %, vol-spike 3×, corr-break
  |ρ|>0.5) à ajouter à `risk_manager`.
- **ECLIPSE — hallucinations LLM (arXiv 2512.03107)** 1/5 — **skipped** : hors de
  notre architecture (pas de LLM génératif dans le cerveau). À garder en réserve
  seulement si un pipeline news-LLM est ajouté (insight : haute confiance = facteur
  de RISQUE, pas de sécurité).
- → **Décisions** : `regime_features.py` (pur, testé) pose 3 primitives ; pistes
  d'intégration : agent **orderflow-entropy** (gating-magnitude), **régime-gating**
  des agents via `up_fraction`/CVIX, **SPA test** + **placebo-reversal** dans le
  backtest, **kill-switch multi-trigger** dans le risque. Rien déployé à l'aveugle.

## §10 — Méthodes de marché (intake Drive `package/PDF`) -> agent STRUCTURE
Extraites des PDF Wyckoff, Volume Profile, ICT/SMC, chandeliers. **Règle d'or :
un pattern/structure isolé n'a PAS d'edge — ce sont des CONFIRMATEURS pondérés
par le contexte, jamais des déclencheurs uniques.**
- **Volume Profile** (déjà codé : `pro_indicators.volume_profile`) — POC = aimant,
  Value Area (≈70 % du volume) = *fair value* ; fade aux extrêmes (prix > VAH ->
  léger short ; < VAL -> léger long), LVN = vide -> cassure rapide.
- **SMC / ICT** -> `price_action.market_structure` : pivots fractals -> tendance
  (HH/HL vs LH/LL) ; **BOS** (break of structure = continuation) vs **CHoCH**
  (change of character = retournement). **FVG** (`fair_value_gaps`) = imbalance
  3 bougies (support/résistance). Breaker block = OB invalidé re-testé (noté, non
  codé : trop discrétionnaire).
- **Chandeliers** -> `price_action.candlestick_patterns` : engulfing, hammer,
  shooting star, doji — **pondération FAIBLE**, gate par contexte.
- **Wyckoff** (spring/UTAD, SOS/SOW, phases) — concepts notés ; la détection
  robuste de *spring* est discrétionnaire -> reportée (pas de faux signal codé à
  l'aveugle).
- → **Décision** : nouvel **`agent_structure`** dans l'essaim (8ᵉ agent) =
  structure (BOS/CHoCH) + position Volume Profile (fade Value Area) + confirmation
  chandelier (faible). `price_action.py` pur + testé.

## §11 — Canon & cadre mental opérationnel (intake Drive `package/PDF`)
Leçons des classiques, distillées en **règles** reliées à nos mécanismes.
- **Douglas, *Trading in the Zone*** — penser en **probabilités** (l'edge est sur N
  trades, pas 1) ; **discipline mécanique** : pas d'override humain d'un signal
  validé sans donnée nouvelle. → garde-fou de décision (préambule des agents
  décideurs ; journaliser tout overruling et son coût).
- **Schwager, *Market Wizards*** — invariants des gagnants : **risque ≤ 1-2 %/trade**,
  edge défini + patience, **stops non négociables**, peu de paris bien choisis,
  journalisation froide. → conforme à nos défauts (`position_sizer` = 1 %/trade ;
  `risk_manager`/`risk_limits` plafonnent positions/perte journalière).
- **Graham, *Investisseur intelligent*** — **marge de sécurité** : en crypto =
  buffer prix↔stop absorbant le bruit normal -> **distance au stop ≥ k×ATR**
  (k fonction du régime CVIX), pas un % fixe. → conforme aux stops ATR existants.
- **Soros, *Alchimie de la finance*** — **réflexivité** : le sentiment façonne les
  fondamentaux ; surveiller les **divergences narrative/réalité**. → piste :
  feature `sentiment_vs_realized` (Fear&Greed vs vol réalisée 30 j) pour l'agent
  sentiment/macro.
- **Dalio, *Principles*** — **believability-weighted decisions** : pondérer chaque
  voix par son track-record vérifié = exactement notre **mixture-of-experts + EARCP**
  (perf+cohérence). Systèmes causaux à délais. → justifie nos hedge weights.
- **Malkiel, *Random Walk*** — beaucoup de « signaux » techniques sont du **bruit
  rationalisé** : antidote à l'overfit -> exiger pour toute feature une **validation
  OOS** (PBO + SPA + placebo-reversal). → renforce §4/§8.
- **Lewis, *Flash Boys*** — le **carnet est un produit, pas une vérité** (spoofing/
  layering ; en perp = wash trades + chasse aux liquidations) -> croiser **depth +
  trades agressifs (CVD)** et exposer un signal de *liquidation hunt*. → conforte
  `agent_orderflow` + `agent_liquidations`.
- **Greenblatt, *Magic Formula*** — **skipped** (value investing equities long
  horizon, hors scope crypto intraday/swing).

## §12 — Architecture multi-agents & apprentissage online (intake Drive)
Les docx « cadre multi-agents / orchestrateur / écosystème autodidacte / Aladdin »
**valident notre architecture** plus qu'ils n'ajoutent du neuf :
- **Mixture-of-experts** (`swarm_brain`) = *believability-weighting* (Dalio, §11) ;
  **orchestrateur** = `agent_hub`/`agent_control`/`agent_loop` ; **hedge/EARCP** =
  apprentissage online. La convergence indépendante est un bon signe.
- **🔒 Frontière de sécurité (VÉRIFIÉE dans le code)** — le principe le plus
  important : **l'apprentissage online ne touche QUE les poids de vote**
  (`learn()` → `save_weights()` → `brain_weights.json`). Les **limites de risque**
  (`risk_manager`/`risk_limits` : kill-switch, caps, perte journalière, levier,
  distance de stop) viennent **exclusivement de l'env/config** (`os.getenv`) et ne
  sont **jamais** modifiées par l'apprentissage. *Ce qui apprend = votes/poids ;
  ce qui est figé = la sécurité.*
- **Sélection de features** : EARCP dégrade déjà les agents non-informatifs (avec
  plancher d'exploration) ; extension possible = score de pertinence par feature
  décroissant sur N décisions sans information mutuelle.
- **Traçabilité anti-hallucination** : chaque agent expose une `note` (donnée
  brute) ; piste = systématiser timestamp + source par vote.
- **Références externes (pas de code copié, LICENSE respectée)** : *TradingAgents*
  (TauricResearch) comme comparatif d'orchestration ; vision **« Crypto-Aladdin
  perso »** (Jasmyne) = risque-portefeuille + agents — xlsx de formules à comparer
  à `position_sizer`/`risk_manager` (suivi, lecture seule).
- **Android/Termux** : Termux est désormais **fournisseur de signaux** (le principal
  est sur **VPS**) ; contraintes à respecter côté signal-provider (task-keeper après
  kill, persistance hors `/tmp`, batterie).

## §13 — Stratégies : agressivité, anti-martingale, pièges (intake Drive)
Docx « agressivité 3/5 & 5/5 », « Martingale », « Black Protocole », « TSLA/XAU/BTC ».
- **Profils d'agressivité** (`risk_profiles.aggressiveness_profile`) : un curseur
  **1..5** contraint sizing/RR/levier/fréquence d'un coup. 3/5 = compromis sain
  (≤2 %/trade, RR≥1.5, levier≤5×). **>3 = `acceptable=False`** (override humain
  requis) ; 5/5 sert de **borne haute** / test de stress du risk manager.
- **🚫 Martingale BANNIE** (`risk_profiles.martingale_guard`) : doubler après une
  perte a un **edge négatif** et converge vers la **ruine** sous tail risk. Règle
  dure : **aucune** hausse de taille après perte **sans nouveau signal indépendant**.
- **Pièges de marché** (`price_action.is_likely_trap`) : faux breakouts / stop hunts
  (mèche au-delà d'un niveau puis clôture revenue du mauvais côté). **Filtre**
  branché dans `agent_structure` : un BOS qui ressemble à un piège est **escompté**
  (0.2 au lieu de 0.5). « Voir le piège, trader le retournement post-piège. »
- **Univers borné** (TSLA/XAU/BTC) : valide `portfolio_scanner` (univers restreint,
  pas de drift) ; or = proxy risk-off (`macro_context`, si source dispo). Renzo
  (restaking ETH) **skipped** (hors scope crypto futures).
- → cibles d'intégration des garde-fous : `risk_manager`/`risk_limits`/
  `config_guard_agent` (pipeline d'ordres) — fonctions pures fournies & testées.

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
- [x] **Coupure de régime de volatilité (CVIX)** — `volatility_regime()` : escompte
      la conviction en stress/extrême, **jamais < 0.6** (module, ne bride pas).
- [x] **Pondération EARCP complète** — `earcp_weights()` : `s=β·P̃+(1−β)·C̃`,
      softmax `η`, plancher d'exploration garanti ; branchée dans `learn()` avec
      cohérence = accord au consensus.
- [x] **Cache TTL + stale-while-error** (`runtime_cache.py`) — optimise la
      dépendance externe au runtime (§7) ; agents réseau enveloppés.
- [x] **Redondance multi-fournisseurs** (`market_sources.py`) — closes Bitget →
      repli CoinGecko (hôte indépendant), derrière le cache. Validé live : 2ᵉ appel
      servi en 0.000 s sans réseau.
- [x] **Pré-chauffe de cache** (`cache_warmer.py`) — peuple les 6 sources d'un
      coup → lectures live locales (cron / boucle légère).
- [ ] Si « plus d'apprentissage » : régression logistique / gradient boosting sur
      bonnes features (jamais un deep net en premier — §1).
- [ ] Enrichissement différé : MCP CoinDesk/Bigdata derrière le cache ; TDLib
      (Telegram) si la compilation est justifiée.

_Références : 2506.05764, 2603.14651, 2412.03167, 2408.03594, 2505.17388,
2112.02947, 2601.06084, 2602.12104, 2501.09404, 2209.05559, 2006.05826,
2604.21297, 2604.20949, 2509.04683 ; Scheffer Nature 2009 ; Guttal/Diks PLOS
One 2015 ; Empirical Economics 57(4) 2019._
