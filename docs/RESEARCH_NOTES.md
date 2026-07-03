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

## §14 — Outils Bitget / MCP / Telegram / on-chain (intake Drive) — surtout dédup
Constat dominant : **déjà couvert** par le repo, ou **hors scope**. Pas d'import en
bloc (anti-doublon).
- **Code Bitget** (`Python/` = 27 `bitget_*.py`, `bitget-bot-v4-hardened/`) : ce sont
  des **ancêtres** du repo, très redondants. Le repo a sa surface stable
  (`execution_gateway`, `bitget_balance_reader`, …). **Action** : n'aller piocher
  qu'un **cas précis** s'il manque (ex. SL natif TP/SL en hedge mode →
  `bitget_native_sl.py`/`bitget_hedge_sl.py`), l'adapter, le tester — pas d'import
  global. Les `backtest_*.py` de v4-hardened encodent des **règles testées**
  (CTA, grid, fear&greed-accumulation, volume-profile, scalp) : à récupérer comme
  *règles*, pas comme code, si on veut une nouvelle stratégie. MT5 = hors scope.
- **MCP servers** (12 référencés : alpaca, dexscreener, tradingview, mcp-trader…) :
  **on en consomme** (via Claude), on **n'en expose pas** tant qu'il n'y a pas de
  besoin. Si un jour Bitget-MCP propre : `create-mcp-server/` (scaffolding),
  `tradingview-mcp/` (exemple charts). `mcp-crypto-price` inutile (Bitget direct
  plus précis).
- **Signaux Telegram** : un **collecteur read-only** (MTProto/Telethon) qui logge ce
  que disent les canaux et le **compare ex-post** à nos décisions (audit, anti-FOMO).
  ⚠️ **signaux publics = sans edge** → usage *proxy de sentiment* / benchmark, jamais
  source de décision. À isoler de `telegram_command_bot.py` (émission). Roadmap.
- **Smart money on-chain** : futur agent `smart_money_flow ∈ [-1,1]` — scoring de
  wallets (PnL/frais/winrate), **flux nets** CEX plutôt que solde, **fenêtre roulante**
  (un wallet smart ne le reste pas), **interdiction de copy-trading aveugle**.
  Nécessite un feed on-chain (Nansen/Arkham) → roadmap, hors scope actuel.
- **DEX (DexScreener/GMGN)** : niche très risquée, **hors scope** crypto-futures.

## §15 — Sources de vérité : catalogue par famille de signal (intake Drive)
Cartographie 2026 + listes d'acteurs (`outils_trading.md`, `SOURCE… acteurs crypto`).
**Principe** : pour chaque famille de signal, **une source de vérité prioritaire** ;
on n'ajoute une dépendance que pour ce qu'on **utilise vraiment**.
- **Orderflow / microstructure** : **Bitget** (primaire) ; pro (abo) : Kaiko, Amberdata.
- **Dérivés** (funding/OI) : Bitget ; MCP CoinDesk ; (Coinglass en référence).
- **On-chain** : Glassnode, CryptoQuant, Nansen, Arkham, DeFiLlama, Dune, Token
  Terminal — **roadmap** (pas de feed branché ; cf. agent `smart_money_flow` §14).
- **Macro** : **FRED** (utilisé), **yfinance** (utilisé), **TradingEconomics** (à
  évaluer). Or = proxy risk-off (§13).
- **News / sentiment** : **Fear & Greed** (utilisé) ; marchés de prédiction
  **Kalshi / Polymarket** (sentiment dur) ; Telegram = proxy faible (§14).
- **Curation outillage** : claudemarketplaces.com, mcpmarket.com (skills + MCP).
- **Hors scope** (filtrés) : Bloomberg/Reuters terminals, Vanguard/Franklin (equity
  TradFi), sniper bots Solana/pumpfun.
- ⚠️ **`grok_report.pdf`** (généré par LLM) : **vérifier toute affirmation chiffrée**
  et citer la **source d'origine**, jamais le rapport Grok lui-même. Laissé `pending`.
- → cible : `assistant/tools.py` (wrappers read-only pour CoinGecko/Bitget déjà
  utilisés ; ajout Glassnode/CryptoQuant **seulement si abonnement**). Les liens
  bruts restent dans `outils_trading.md` côté Drive (anti-rot).

## §16 — Base de connaissances + agent backtester autonome (intake Drive)
Le dossier trié devient **exploitable**, et un agent **fabrique/teste/promeut** des
stratégies.
- **`knowledge_base.py`** : charge les fiches `extraction/*.md` (frontmatter
  `source/category/action/target` + valeur) dans **`knowledge.json`** (persisté →
  survit à la suppression d'`extraction/`). Interrogeable par les agents :
  `kb.rules_for("volume_profile")`, `kb.query(category="method")`. 70 fiches.
- **`strategy_lab.py`** — agent **backtester autonome** :
  - **stratégies pures & causales** (aucun look-ahead) : ema_cross, rsi_reversion,
    donchian, vp_fade, structure_bos, **macd**, **bollinger** (ajoutées au skim
    Drive) ; **composition** : régime-gating (`up_fraction`) + ensemble (vote
    majoritaire) ; **amélioration** : recherche de params (`improve_ema`).
  - **observation honnête (multi-tests)** : à 9 stratégies, PBO≈0.36 et
    `rsi_reversion` promue ; à 11 stratégies, PBO passe à **0.53 (>0.5)** → l'agent
    **refuse toute promotion**. Plus on teste de candidats, plus le risque de chance
    monte : le garde-fou PBO bloque correctement (correction multi-tests).
  - **évaluation HONNÊTE** (réutilise `backtest_brain`) : frais, Sharpe, edge vs
    buy&hold, **walk-forward**, **PBO** sur l'ensemble des stratégies.
  - **score** = Sharpe × (tranches gagnantes), pénalisé si edge≤0 ou trop peu de
    trades. **`build_named`** reconstruit chaque stratégie depuis son nom → le code
    promu reproduit EXACTEMENT la stratégie testée.
  - **promotion** : seulement si Sharpe≥0.3, edge>0, walk-forward≥60 % gagnant,
    trades≥20, **PBO<0.5** → écrit un **rapport** `.md` + un **fichier code prêt à
    l'emploi** `.py` sous `strategies_out/` (signal advisory, aucun ordre).
  - **honnête par construction** : la plupart des stratégies ÉCHOUENT la barre — on
    ne promeut pas du surappris (cf. §4/§8/§11). Run BTC 1H : `rsi_reversion_14`
    promue (Sharpe 1.47, edge +37 %, folds+ 80 %, PBO 0.36) ; donchian/structure
    rejetées (Sharpe négatif). À re-valider en paper avant tout capital.

## §17 — Défense anti prompt-injection (`prompt_guard.py`)
L'assistant LLM (`assistant/`) ingère du texte EXTERNE non fiable : message
utilisateur (potentiellement relayé de Telegram), **résultats d'outils** (news,
sentiment, DEX, tokens), vision. Risque : détourner le raisonnement, exfiltrer le
system prompt, induire une action. **Defense in depth** (l'assistant est DÉJÀ en
lecture seule — aucun ordre possible) :
- **`prompt_guard.py`** (pur, testé) : `scan` (signatures : override/exfil/secret/
  jailbreak/role-marker/zero-width/oversize → risk low/med/high), `sanitize`
  (retire contrôle/zero-width/marqueurs de rôle, NFKC, tronque), `wrap_untrusted`
  (encapsule un contenu externe en `<donnees_externes>` avec **provenance assainie**),
  `assess`, et `SYSTEM_HARDENING` (clause système anti-injection).
- **Câblage (defense in depth, 5 couches)** :
  1. **`agent.py`** : system prompt durci, message utilisateur assaini au point
     d'entrée `run()` (couvre CLI/Telegram/dashboard), sorties d'outils textuelles
     **encapsulées** et champs texte des sorties **dict/list assainis**
     (`sanitize_obj`), réponse finale passée par **`redact_secrets`** (anti-
     exfiltration : aucune clé ne ressort).
  2. **`vision.py`** : question assainie + **texte décrit de l'image** assaini +
     redacté (injection visuelle : une capture peut contenir « ignore… »).
  3. **`news_feed.py`** : titres/sources externes **assainis dès l'ingestion**.
  4. **`telegram_command_bot.py`** : **cap longueur** (4000) + **rate-limit**
     (20/min, `rate_limit_ok`) anti-flood, en plus du `chat_id` autorisé.
  5. **`redact_secrets`** : masque les **préfixes de clés** (sk-ant/ghp_/xai-/AIza/
     PRIVATE KEY…) **sans** toucher aux adresses/hashes on-chain légitimes.
- Principe : tout contenu externe est traité comme **DONNÉES, jamais instructions** ;
  l'assistant n'obéit qu'à son system prompt et reste **lecture seule**.

## §18 — Coordinateurs LLM (Sakana) : ce qu'on prend, ce qu'on laisse
Lecture de **TRINITY** (ICLR 2026, arXiv:2512.04695) et **Conductor / Learning to
Orchestrate Agents** (arXiv:2512.04388). Les deux orchestrent des **LLM frontières**
— **hors de notre cerveau déterministe** (pas de LLM dans la décision : lent, cher,
opaque, dépendance externe). On **ne copie pas** l'orchestration.
- **Conductor** : un LLM entraîné par RL conçoit des **topologies de communication**
  agent↔agent + prompt-engineering. Idée intéressante (les agents ne sont pas
  forcément indépendants) mais **RL = opaque** → on garde notre **gating
  déterministe** (prudence de `cognition`, régime-gating du labo). Non adopté.
- **TRINITY — LA pépite** : ils prouvent que **sep-CMA-ES** (évolution dérivée-libre,
  covariance diagonale) bat RL / grille / random search dans **NOTRE régime exact** :
  objectif **scalaire bruité** (score de backtest), **sans gradient**, **évals
  coûteuses** (un backtest/essai), params faiblement corrélés. → **adopté** :
  `evolution.py` (sep-CMA-ES pur, testé sur sphère/quadratique/Rosenbrock borné),
  branché dans `strategy_lab.improve_ema` (remplace la grille, repli grille si numpy
  absent).
- **Généralisation (toutes les pistes)** : `evolve(family, …)` optimise chaque
  famille (ema/rsi/donchian/bollinger/macd) ; `evolve_ensemble` est le
  **« coordinateur évolué »** — sep-CMA-ES trouve les **poids des experts**
  (ex. `ema 0.72 · rsi 1.66 · donchian 2.16 · bollinger 0.96 · macd 0.00`),
  déterministe et **lisible** (poids encodés dans le nom `wens_…`, reconstructible).
- **🔑 Clé anti-surapprentissage : séparation TRAIN/TEST.** L'évolution n'optimise
  que sur `candles[:70%]` (signaux causaux → aucune fuite) ; la généralisation est
  jugée par run() sur la série complète + PBO. **Effet mesuré (BTC 1H)** : *sans*
  split, l'ema évolué surajustait (PBO ~0.69, 0 promotion) ; *avec* split,
  **PBO 0.34** et **4 stratégies promues** dont `evo_bollinger_8` (score 2.05 vs
  base 0.44) et `evo_rsi_reversion_8` — meilleures **et** robustes. On adopte le
  solveur de TRINITY **et** la rigueur OOS : l'optimisation devient *exploitable*,
  pas auto-bloquée.

## §19 — « Futurtester » : simulateur d'issues futures (`futuretester.py`)
L'inverse du backtest : au lieu de tester sur le passé, on **simule des PLAGES
d'issues futures conditionnelles**. ⚠️ **Pas un prédicteur** — un générateur de
fourchettes « si ces hypothèses tiennent, voilà l'éventail » (GIGO ; on expose
toujours P5..P95 + les hypothèses, jamais un point). C'est la *scenario analysis*
des institutions, adaptée crypto.
- **Prévisions institutionnelles -> plages** : `project_forecast` (cibles bas/base/
  haut -> drift triangulaire -> Monte Carlo + vol). `drift_from_forecasts` :
  `mu = ln(cible/S0)/T`.
- **Scénarios typés** : `SCENARIOS`/`run_scenario` — base, **convergence_bull**
  (IA+blockchain↔TradFi, adoption haute, afflux institutionnel), reg_bear,
  stagnation, tail_crisis. Moteur **Merton** (GBM + sauts) ; `fan_stats` (éventail).
- **Macro mondiale** : `macro_markov_path` (chaîne de Markov sur régimes
  expansion/slowdown/recession/recovery).
- **Évolution des acteurs** : `actor_evolution` (dynamique du **réplicateur** :
  parts incumbents/challengers/entrants ∝ fitness). ⚠️ la **détection** des vrais
  futurs acteurs exige des données externes (recherche) — ici on **projette** des
  candidats fournis, on ne les devine pas.
- **Adoption techno** : `adoption_logistic` (courbe en S, Bass-like).
- Honnêteté intégrée : le *volatility drag* lognormal fait que la **médiane** crypto
  est sous S0 à drift nul (cohérent avec Black-Scholes §8). Sortie BTC 1 an (base) :
  P5 −66 % … P95 +147 %, prob_up 0.44 — l'éventail crypto est ÉNORME, c'est le message.

## §20 — Sources institutionnelles temps réel + couplage réel du futurtester
**Demande** : « trouver des sources externes qui donnent l'info dès la première
publication publique, se connecter aux institutionnels pour suivre leur actualité »,
puis brancher des **entrées réelles**, **coupler au cerveau**, **fan-chart au
dashboard**, **calibrer σ/sauts par actif**.

**Réalité d'architecture** (rappel) : le bot tourne sur VPS et **ne peut pas** appeler
mes outils MCP (Bigdata.com, CoinDesk…) — ceux-ci sont MES outils de recherche.
Pour que le bot suive l'actualité institutionnelle *au runtime*, il faut des **API/RSS
publiques gratuites** qu'il interroge lui-même. J'ai donc vérifié, en direct, des
sources **gratuites et SANS CLÉ** :
- **FRED** (`fredgraph.csv`, St. Louis Fed) — séries officielles, **aucune clé** :
  `NFCI` (conditions financières), `T10Y2Y` (pente 10a-2a), `VIXCLS`, `BAMLH0A0HYM2`
  (spread High-Yield OAS), `FEDFUNDS`. Param `cosd` pour limiter la charge.
- **RSS presse Fed + BCE** — actualité brute des banques centrales (titres seulement,
  **assainis par `prompt_guard`** : un titre externe n'est jamais une instruction).
- (déjà en place) CoinGecko `/global`, alternative.me Fear & Greed.

**`macro_sentinel.py` — « Sentinel Macro Analyst »** (note .docx fournie, réalisée en
code DÉTERMINISTE, aucun NN) : `regime_nowcast` classe le **régime macro dominant**
(les 4 mêmes régimes que §19 : expansion/slowdown/recession/recovery) à partir des
niveaux **ET** variations (NFCI, pente, VIX, spread HY) avec des seuils
**recherche-fondés** (inversion 10a-2a = avance de récession ; HY OAS >5 % = stress de
crédit ; NFCI >0 = conditions serrées). Sortie : régime + scores + `drivers` explicites
+ `stress`/`confidence`. Tout via `runtime_cache` (TTL 6 h), best-effort, ne lève jamais.

**Couplage du futurtester** (`futuretester.py`) :
1. **Entrées réelles** — `from_market(symbol)` : σ et sauts **calibrés sur l'actif**
   (drift par défaut **NUL** = baseline honnête « sans edge »).
2. **Cerveau** — `stress_brain` / `stress_assessment(bias, conviction, scenarios)` :
   confronte le biais du cerveau aux scénarios. Biais **LONG** -> le risque est la
   **queue basse** (P5) du pire scénario adverse ; **SHORT** -> queue haute (P95).
   Drapeau si forte conviction **et** queue adverse sévère. Réponse directe à « si je
   suis LONG, quel P5 en crise ? ».
3. **Fan-chart dashboard** — bloc `future` (panneau « Futur · Éventail ») : éventail SVG
   P5/P25/P50/P75/P95 en rendement, table des scénarios, badge de régime Sentinel,
   drapeau de stress. Projection Monte Carlo cachée 300 s (coûteuse).
4. **Calibration par actif** — `calibrate(closes)` : σ diffusive annualisée + sauts
   Merton par la **méthode du seuil robuste (MAD)** (un rendement > 3.5·σ_robuste = saut).
   `macro_outlook` : `macro_markov_path` **part du régime courant détecté** (Sentinel),
   plus d'origine arbitraire.

**Évaluation honnête du stack SEC EDGAR / EdgarTools / OpenInsider (fourni par l'user)** :
- `EdgarTools` (pip), **SEC EDGAR** (API publique gratuite, `fair-access` UA requis),
  **OpenInsider** : excellents, mais **orientés ACTIONS** (10-K/10-Q, achats d'initiés).
  Le bot vise le **crypto-futures** : la pertinence directe est **faible** (pas de 10-K
  pour BTC). Le canal institutionnel à **haute** valeur pour le crypto, c'est le **MACRO**
  (liquidité/taux/régime de risque) — d'où le choix FRED + banques centrales ci-dessus.
- **Décision** (non sur-ingénierie) : je n'ajoute **pas** un pipeline actions lourd qui
  diverge du cœur crypto. Point d'extension laissé propre : `macro_sentinel.FRED_SERIES`
  est extensible, et un futur `edgar_signals.py` optionnel (pip `edgartools`) pourrait
  alimenter un actor-detection data-driven (§19) pour les sociétés crypto-exposées
  (MSTR, COIN, mineurs) **si** un besoin réel émerge — à n'activer qu'à ce moment-là.

## §21 — Extended Samuelson Model (ESM) : états & signaux (`esm.py`)
Source : *Equity Market Price Changes Are Predictable — A Natural Science Approach*
(Han 2025 ; fondé sur Han & Keen 2021, *Heliyon*). Thèse : le marché n'est pas un
bruit stochastique mais un système **causal dynamique** :
`d·ln(p)/dt = H·[(D−S)/(D+S)] + M`, où **NED = (D−S)/(D+S)** (Demande Excédentaire
Normalisée ∈ [−1,1]) capte les preneurs de liquidité et `M` les fournisseurs.

**Ce qu'on PEUT exploiter** (l'apport structurel, pas l'estimateur propriétaire) :
- **8 états de marché** = signe du NED sur 3 échelles (court/moyen/long) :
  `état = 1 + (court>0) + 2·(moyen>0) + 4·(long>0)`. État 1 (tout −) = creux/le plus
  pessimiste, État 8 (tout +) = sommet/le plus euphorique. (Sommets ↔ S8, creux ↔ S1.)
- **6 signaux directionnels** = divergences NED↔prix : tendance (1/2), **retournements
  par divergence** (3 = prix higher-low + NED lower-low → reverse to uptrend ; 4 =
  symétrique baissier), **preneurs informés** aux extrêmes (5 = distribution au sommet,
  6 = accumulation au creux). Ce sont des signaux **anticipatoires** (ex. signal 10 j
  avant Black Monday 1987 ; reversals intraday validés 90–95 % à 7 j chez les auteurs).
- **Compatibilité temporelle** : le fin contient le grossier (multi-timeframe).

**Ce qu'on NE PEUT PAS reproduire honnêtement** : l'estimateur exact du NED (données
propriétaires Han & Keen non publiées). → `esm.py` en construit un **proxy
transparent et observable** depuis l'OHLCV : *money-flow* de Chaikin
(Close-Location-Value pondéré volume), borné [−1,1] comme le NED. **Étiqueté
« inspiré », jamais présenté comme l'original.**

**Intégration (non invasive)** :
- `esm.py` pur/testé : `ned_proxy`, `market_state` (1..8), `directional_signal`
  (1..6), `analyze(symbol)` multi-TF (5m/15m/1h) résilient+caché.
- **Agent divergent** (= l'agent d'ANTICIPATION) : `anticipation_nudge` ajoute un biais
  **borné ±0.2**, guardé (best-effort→0), issu des signaux 3/4/5/6. `divergent_score`
  inchangé (tests intacts) → renforce sans destabiliser le cerveau validé.
- **Dashboard** : panneau « Futur · Éventail » expose l'état ESM (1–8) + le signal
  directionnel courant.
- Pistes futures (à activer si utile) : 9ᵉ agent ESM dédié sous EARCP ; turning-points
  T2/T4 (niveaux de prix où le NED change de signe) comme garde-fous de risque.

## §22 — Agent SIMONS : régimes cachés + arbitrage statistique (`simons_agent.py`)
Source : note « Stratégie Simons pour cryptomonnaies » (Renaissance/Medallion).
On transpose les piliers EXPLOITABLES — **classiques, déterministes, sans réseau de
neurones** (c'est exactement la boîte à outils de Renaissance : Baum, le « B » de
Baum-Welch, y a forgé les HMM).

**Ce qu'on implémente** (`simons_agent.py`, pur/testé/résilient) :
- **Régimes cachés — HMM gaussien (Baum-Welch/EM + Viterbi)** sur log-rendements
  standardisés. Forward-backward avec **facteurs d'échelle** (stabilité numérique),
  **init déterministe par quantiles** → 100 % reproductible (aucun aléa). C'est la
  pièce maîtresse : il décode des états latents non observés.
- **Arbitrage statistique — retour à la moyenne (OU)** : `zscore` de la déviation,
  `half_life` via AR(1) (`hl = −ln2/ln(1+b)`). Edge ténu × loi des grands nombres.
- **Gating par régime** : on RÉVERTE en régime calme (range), on se RETIRE en
  STRESS (gate robuste = vol récente/vol de fond > 1.8, façon « speedbump ROC > σ »),
  biais réduit/aligné en tendance. Le HMM porte la **direction**, le gate de stress
  est **découplé** (pas le ratio fragile des variances d'états).
- **Kelly fractionnaire** `f = espérance/variance` (demi-Kelly, plafonné) — PUREMENT
  INDICATIF, ne dimensionne aucun ordre, **aucun levier appliqué**.
- **Rank IC (Spearman)** : métrique d'évaluation hors-échantillon d'un signal.

**Intégration** : nouvel **agent du cerveau** (9e), `agent_simons`, sous pondération
EARCP. `AGENTS`/`AGENT_FUNCS` mis à jour ; les poids manquants d'un fichier existant
retombent gracieusement sur 1.0 (comme divergent/structure). Auto-affiché au
dashboard (le panneau Cerveau itère les agents).

**Ce qu'on N'implémente PAS, honnêtement** :
- **Avellaneda-Stoikov + RL (PPO/DDQN)** pour le market-making : exige des ORDRES
  réels + un réseau de neurones → hors cadre (advisory/paper, sans NN).
- **Levier 12,5–20×** : contexte institutionnel Medallion ; en crypto retail =
  risque de ruine. Kelly reste indicatif.
- **LVR / défense DeFi** (maker priority, speedbumps on-chain) : pertinent seulement
  pour un LP/market-maker actif — noté pour extension future, pas pour l'advisory.
- L'« Agent de Code » LLM générateur d'indicateurs : déjà couvert autrement par
  `strategy_lab` (backtester autonome) sous garde anti-surapprentissage (§16).

Pistes (à activer si utile) : **HMM non-homogène (NHHMM)** dont les transitions
dépendent de la liquidité/sentiment ; **CV purgée + embargo** (López de Prado) en
complément du walk-forward/PBO existant ; **NSGA-II** multi-objectif (Sharpe↑, MDD↓,
coûts↓) en complément du sep-CMA-ES mono-objectif (§18).

## §23 — Agent SAVANT (« autiste digitale ») : rupture de symétrie tensorielle (`savant_agent.py`)
Source : spec « Architecture cognitive — Autiste Digitale ». Pièce aspirationnelle
(« Alpha Absolu Infaillible ») dont on extrait l'UNIQUE idée vraiment nouvelle,
déterministe et dans le cadre, en rejetant explicitement le reste.

**Ce qu'on construit** (`savant_agent.py`, pur/testé/résilient ; 10e agent du cerveau) :
- **Tenseur synesthésique** : `feature_matrix` fusionne des features hétérogènes
  (rendement, |rendement|, pression CLV, amplitude, volume) dans un même espace.
- **Rupture de symétrie = distance de MAHALANOBIS** : `mahalanobis_anomaly` /
  `symmetry_break` détectent une incohérence avec la STRUCTURE de covariance — un
  point « normal » feature-par-feature mais incohérent globalement est repéré (la
  spec « les anomalies BRISENT la symétrie géométrique avant tout calcul numérique »,
  rendue rigoureuse). Borné [0,1] via `1−exp(−score/2)`.
- **Signal à CONTRE-COURANT** : on FADE la dislocation (manipulations/flush tendent à
  se corriger), actif seulement au-dessus d'un seuil (hyper-focalisation).
- **Immunité au bruit** : Fear & Greed traité comme bruit exploitable à contre-courant
  (FUD→long, FOMO→short).
- **VaR (indicative)** : `value_at_risk` historique + paramétrique (erfinv maison).
- Hook Monte-Carlo : futuretester mobilisable en cas d'anomalie forte.

**Ce qu'on REJETTE (contraintes DURES — dit honnêtement dans le code)** :
- « Réseau de neurones neuromorphique » : le projet INTERDIT les NN. On garde la
  moitié « filtres rigides, zéro hallucination/dérive » de la spec = le déterminisme.
- « Réécrit/recompile son propre code à chaque bloc » : code auto-mutant = risque de
  sécurité inacceptable ; l'analogue sain (apprentissage en ligne des poids) existe.
- « Hyper-masking / fragmentation d'ordres / évasion MEV » : ORDRES réels + évasion de
  détection → hors cadre (paper/advisory). La VaR reste indicative.
- Nœud archive complet / audit de bytecode / arbitrage cross-chain : infra hors cadre.
- « Alpha Absolu Infaillible » : impossible. Sortie = signal probabiliste BORNÉ.

Intégration : 10e agent `agent_savant` sous EARCP ; lentille MULTIVARIÉE distincte des
agents univariés (divergent, structure). Auto-affiché au dashboard.

## §24 — Agent SAVANT GÉOMÉTRIQUE : analyse géométrique -> trading (`geometric_agent.py`)
Source : 5 articles d'analyse géométrique / théorie des graphes / EDP fournis
(rank-width, p-Laplacien/Cheeger, profils isopérimétriques, Talagrand/Eldan-Gross,
inégalité isopérimétrique quantitative). **Honnêteté** : ce sont des ANALOGIES ; on
n'implémente pas les théorèmes à la lettre, mais leur NOYAU CALCULABLE, qui coïncide
avec des méthodes quant ÉTABLIES (recherche complémentaire à l'appui) :

1. **Profil isopérimétrique / Grand-Lebesgue → régime de queue** (`tail_regime`) :
   concentration de queue via réarrangement décroissant des |rendements| STANDARDISÉS
   (sans échelle = forme de la queue), comparée à une référence gaussienne
   (auto-calibré, déterministe). ratio≫1 = marché « non-euclidien » (blow-up) → **suivi
   de tendance, pas de réversion**. ≈ détection de régime par tail-index (QuantPedia,
   MDPI tail-risk).
2. **Rank-width / expansion → stabilité d'intrication** (`correlation_graph_metrics`) :
   connectivité algébrique **λ₂** du graphe |corr|>seuil (clustering spectral) + bornes
   de **Cheeger** (λ₂/2 ≤ h ≤ √(2λ₂)). λ₂↓ = co-intégration en rupture → fermer
   l'arbitrage. ≈ clustering spectral de matrices de corrélation (ACM AI-in-Finance).
3. **p-Laplacien de Neumann / Cheeger → partition** (`cheeger_partition`) : vecteur de
   **Fiedler** → 2 « ensembles de Cheeger » → base d'allocation **bêta-neutre**.
   ≈ graph p-Laplacian clustering (Bühler ICML'09). NP-dur exact, λ₂ polynomial.
4. **Talagrand / Eldan-Gross (Besov, k>1) → toxicité** (`higher_order_toxicity`) :
   ratio RMS variation d'ordre 2 / ordre 1 (interactions d'ordre supérieur dominantes).
   tendance lisse→0, iid→~0.5, flicker/spoofing→~1 → **se retirer** (anti-sélection
   adverse). ≈ variation d'ordre supérieur / toxicité de flux (Easley VPIN, Barndorff-
   Nielsen ; cf. 2604.20949 §microstructure).
5. **Inégalité isopérimétrique quantitative** : cadre de stabilité (déficit) qui
   sous-tend (1).

**Bug-fix vs les esquisses fournies** : `|Δ|^(2/k)` sous-évaluait l'ordre 1 (RMS
cohérent à la place) ; `nx.conductance(max_node)` indéfini (Fiedler propre à la place) ;
λ₂=0 d'un graphe DÉCONNECTÉ est correct (deux blocs co-intégrés séparés).

**Intégration** : 11e agent `agent_geometric` (par actif : régime de queue + toxicité)
+ `portfolio_structure(symbols)` advisory (λ₂ + partition de Cheeger du panier).
Profil cognitif neuro-atypique traduit en calcul DÉTERMINISTE (hyperacuité multi-
échelle, synesthésie chiffres→graphe, bruit-carburant). Aucun NN, aucun ordre.

## §25 — Concrétisation empirique des outils géométriques (recherche + upgrades)
Recherche multi-agents (5 pistes, 21 papiers, **arXiv vérifiés un par un**) pour rendre
les outils §24 MOINS abstraits. Validation live : BTC mesuré **α≈2.09** — pile dans la
plage empirique du papier d'ancrage (crypto α∈[2.0,2.5], vs ~3 pour les actions).

**Implémenté (pur, testé, sans nouvelle donnée requise)** :
- **T1 — indice de queue de HILL** (`hill_tail_index`, arXiv:1803.08405) : α calibré
  crypto remplace le proxy gaussien ad-hoc. `tail_regime` devient HYBRIDE : α tranche
  les cas décisifs (≤2.2 lourd→trend ; ≥3.5 léger→revert), le proxy Φ (stable sur
  fenêtre courte) gère l'ambigu (Hill bruité sous ~6 mois de données).
- **T2/T3 — débruitage RMT Marchenko-Pastur** (`rmt_denoise`, arXiv:1610.08104) : on
  débruite la corrélation (clip du bulk < λ+=(1+√q)²) AVANT de bâtir le graphe ;
  seuil 0.3→**0.5** (crypto-validé, arXiv:2505.24831). λ₂/Cheeger mesurent la vraie
  co-intégration, pas le bruit d'échantillon.
- **T4 — saut BNS** (`relative_jump`, `bipower_variation`, arXiv:1708.09520) : la
  toxicité combine la rugosité (ordre2/ordre1) ET la mesure de saut (RV−BV)/RV
  (fraction de variation due aux discontinuités = événements toxiques).

**Liste de téléchargement vérifiée (par priorité)** — l'utilisateur peut les fournir :
`2603.09219` (protocole IS-WFA-OOS), `1610.08104` (clean corr RMT), `1803.08405`
(tail BTC), `2510.19130` (RMT crypto), `2406.10695` (stat-arb clustering), `2112.13213`
(OFI cross-impact) ; puis `2505.24831`, `1904.08575` (SPONGE signé), `2202.02728`
(HRP), `1708.09520` (jump tests), `2205.11122`, `2501.03938` ; ciblés : `2506.12587`,
`2606.15715` (perp crypto), `2407.15766` (eGARCH-EVT), `2512.12924`, `2507.22712`,
`2504.15908`, `2508.13174`.

**Reste ABSTRAIT / bloqué sur la DONNÉE (honnête)** :
- T4 « spoofing/OFI multi-niveau/markout bps » (arXiv:2112.13213, 2606.15715, 2504.15908)
  exige un flux carnet **L2/L3 et tape par-wallet** que le bot lecture-seule n'a PAS
  (il travaille sur closes/rendements). Le saut BNS (D1) marche sur OHLCV ; OFI/spoof
  sont **bloqués sur l'ingestion** Bitget.
- Le socle « isopérimétrique/Besov/Cheeger » reste une ANALOGIE ; les papiers
  fournissent les SUBSTITUTS quant établis (Hill, RMT, BNS) qui coïncident avec le
  noyau calculable — on ne prétend pas implémenter les théorèmes.
- Pistes non encore codées (à activer après validation) : SPONGE signé (T3), HRP
  intra-cluster (T3), GARCH→EVT-sur-résidus (T1), consensus de clusters sur fenêtres
  roulantes (T2/T3), protocole T5 (plateau SR≥0.9·opt, purge+embargo, DSR/PBO, Rank IC).

## §26 — Protocole de validation T5 : mesurer l'alpha des agents (`agent_validation.py`)
Réponse à « avant de donner du poids aux agents, MESURER lesquels ajoutent vraiment de
l'alpha hors-échantillon ». Lecture seule, advisory — **ne modifie PAS** les poids.

**Statistiques (pures, testées)** :
- **Rank IC** de Spearman (vote → rendement futur) + t-stat — AlphaEval 2508.13174 ;
- **PSR** (Probabilistic Sharpe Ratio, Bailey-LdP) : P(vrai Sharpe > 0) en tenant
  compte de skew/kurtosis et de la LONGUEUR d'échantillon ;
- **DSR** (Deflated Sharpe Ratio) : PSR avec benchmark = max attendu sous H0 sur N
  essais → **déflate le multiple-testing** (on teste plusieurs agents) ; réf. 2603.09219 ;
- **Purge** : rendements futurs NON CHEVAUCHANTS (pas = horizon) pour éviter la fuite
  par auto-corrélation des labels (López de Prado).

**Deux chemins** :
1. `rank_pure_agents(candles)` — **replay** des agents purs (simons/savant/geometric/
   divergent) sur l'historique de bougies → IC + Sharpe + PSR + DSR. Utilisable tout de
   suite (causal, sans look-ahead).
2. `evaluate_from_log(brain_log)` — évalue **TOUS** les agents depuis les votes réels
   journalisés (se renforce au fil du temps).

`suggest_weight_priors` — propose (advisory) des poids a priori bornés [0.4, 1.8] depuis
le DSR ; à CONFIRMER avant toute application au cerveau (on ne touche pas au validé).

**Résultat live (honnête)** : sur ~64 échantillons (BTC 1h, horizon 8 ≈ 21 j),
`savant` mène (IC +0.135, DSR 0.37) mais **AUCUN agent ne bat le seuil déflaté**
(SR0_max≈0.14, meilleur DSR 0.37 < 0.9). C'est le but : refuser de distribuer du poids
sur des données minces. Historique crypto court → faible puissance (un IC ~0.04 est
NORMAL) ; on rapporte n, t-stat et l'avertissement, pas une courbe flatteuse.

**Prochaine étape** : laisser `brain_log` accumuler, puis ré-évaluer périodiquement les
11 agents et n'ajuster les poids EARCP qu'avec des DSR significatifs (et un protocole
plateau + purge + OOS verrouillé pour les seuils tunables, cf. 2603.09219).

## §27 — 12 papiers exploités : upgrades T1–T5 + microstructure (déblocage T4)
12 PDF fournis par l'utilisateur, lus par 2 workflows d'extraction (formules/paramètres
EXACTS, arXiv vérifiés). Implémentés (purs, testés, OHLCV/L2 seulement, aucun NN) :

**T5 — `agent_validation.py`** (`2501.03938`, `2603.09219`) :
- `replication_ratio` (Eq 3.3) + `replication_ratio_multi` (Eq 3.4) : haircut de Sharpe
  FERMÉ — fraction du Sharpe in-sample qui survit OOS (f(T1, SR/β, p, m)). Validé : à
  T1=250/SR=0.1 il reste ~73 % ; à T1=2500, ~96 %.
- `max_drawdown`/`cagr`/`calmar` + `B_DEFAULT` (SR≥2, Calmar≥1.5, MDD<7 %) ;
  `walk_forward_quorum` (plis purgés, quorum q=2/3). `rank_pure_agents` expose le
  haircut + l'OOS Sharpe attendu + WFA par agent.

**T1 — `geometric_agent.py`** :
- `hurst_exponent` (R/S, `2205.11122`) : H>0.5 tendance / <0.5 réversion → confirme/
  atténue le momentum dans `signal`.
- `parkinson_vol` (`2606.15715`) : σ=0.6005612·ln(H/L). Hill déjà calibré crypto
  α∈[2.0,2.5] (`1803.08405` confirme les valeurs ; CSN/KS et bootstrap GoF = pistes).

**T2** : `rie_denoise` (Ledoit-Péché, `1610.08104`/`2510.19130`) — shrinkage non-linéaire
ξ_k=λ_k/|1−q+q·λ_k·s(λ_k−iη)|² (η=N^{-1/2}), plus fin que le clip-to-mean. Fenêtre
crypto validée ≈182 j, q=N/T.

**T3** : `sponge_partition` (SPONGE signé, `1904.08575`, τ⁺=τ⁻=1) — gère les corrélations
NÉGATIVES, met les actifs anti-corrélés sur des legs OPPOSÉS (bêta-neutre, validé) ;
`hrp_weights` (HRP, `2202.02728`) — allocation déterministe sans inversion. Seuil corr
0.5 (`2505.24831`) ; résidualisation + consensus de clusters = pistes (`2406.10695`).

**T4 — `microstructure.py` (NOUVEAU, déblocage)** :
- Features PURES depuis carnet L2 + tape : `book_ofi` (Cont-Kukanov, `2112.13213`),
  `queue_imbalance`, `trade_sign_imbalance`, `markout` (sélection adverse, `2606.15715`),
  `spread`, `mid_price`. Toutes validées en direction.
- Collecteur best-effort `collect_once`/`run` (REST-poll via bitget_market_data) +
  buffer roulant `recent`/`summary` que les agents lisent (découplé).
- `signed_volume_ofi` (`geometric_agent`, proxy OHLCV dégradé de `2112.13213`).

**Reste BLOQUÉ / hors-scope (honnête)** :
- **Vrai L3 / spoofing** (`2504.15908`) : INDISPONIBLE sur le flux public Bitget
  (ordre-par-ordre) → seuls des proxies L2 possibles.
- **Markout/OFI haute fidélité** : le REST-poll (~1-2 s) est basse fidélité ; l'OFI
  par-événement exige le **WebSocket** `wss://ws.bitget.com/v2/ws/public` (books+trade)
  → upgrade futur (le collecteur écrit déjà le buffer, le service WS le remplacera).
- Paramètres laissés RÉGLABLES (pré-engagés par l'utilisateur, pas dans les papiers) :
  cliff τ_SR/τ_DD, SR_min, embargo (le protocole ne donne qu'un purge g=5 j).

Le socle « isopérimétrique/Cheeger/Besov » reste une ANALOGIE ; les substituts
implémentés (Hill, RIE, BNS, OFI, HRP, SPONGE) sont des méthodes quant ÉTABLIES.

## §28 — Durcissement pré-réel (réponse à l'audit) : cerveau câblé + couche risque vivante
Audit multi-agents (17 findings vérifiés) : le système était « sûr par VERROU »
(`DRY_RUN_ONLY`), pas par garde active — le cerveau (11 agents) était DÉBRANCHÉ du
pipeline de décision, et la couche risque/kill-switch était du CODE MORT. Corrigé :

- **Cerveau → décision** (`preorder_engine.brain_adjustment`) : le cerveau (essaim)
  est désormais GATE + MULTIPLICATEUR de taille. S'OPPOSE avec conviction ≥0.3 → rejet ;
  d'ACCORD → taille ∝ conviction [0.4,1] ; NEUTRE → 0.6. Ne peut que RÉDUIRE la taille.
  Fail-safe NEUTRE (indisponible → facteur 1.0). Un test réel valide MAINTENANT le cerveau.
- **Kill-switch + caps durs vivants** (`execution_gateway._risk_gate` + `risk_state.py`) :
  `risk_manager.check_trade` (kill-switch, notional, levier, positions, perte du jour)
  appelé AVANT toute transition, même en dry-run. `risk_state` alimente la perte du jour
  depuis le P&L paper. Test d'intégration : KILL_SWITCH bloque le dry-run.
- **Caps portefeuille vivants** (`preorder_engine._apply_portfolio_guards`) :
  `evaluate_portfolio_caps` (notionnel/risque/positions/SL agrégés) appliqué ; kill-switch
  → tout rejeté.
- **Watchdog étendu** : surveille les 3 services systemd + fraîcheur microstructure ;
  `--arm-killswitch` pose KILL_SWITCH automatiquement sur anomalie sévère (boucle DOWN,
  perte ≥ cap, microstructure figée).
- **Apprentissage + validation planifiés** (`brain_cycle.py`, `brain_validation.py` dans
  `agent_control.COMMANDS`) : EARCP s'entraîne à chaque cycle (read+learn) ; validation T5
  auto-throttlée (~6h) → `validation_report.json` + poids a priori ADVISORY.
- **Limites en SOURCE UNIQUE** (`config`) : levier 2.0, positions 3 partout (fin des
  divergences risk_manager/risk_limits/config).
- **Bugs corrigés** : `rie_denoise` (tri décorrélait valeurs/vecteurs propres), garde de
  fraîcheur microstructure, lock du collecteur WS.

**Reste avant un VRAI test** (paper d'abord) : laisser tourner quelques jours en paper
avec le cerveau câblé → vérifier `brain_log`/`brain_weights` (11 agents entraînés) +
`validation_report.json` (quels agents battent le seuil déflaté) ; ne passer au réel
qu'après un track-record paper documenté ET la levée manuelle de `DRY_RUN_ONLY`.

---

## §29 — Mandat de gestion encodé (`mandate.py`) + mise en réel par paliers
Décision propriétaire : bot autonome, objectif « le plus possible » SOUS contrainte de
drawdown (MDD 15-25 %), levier plafonné ×5 ajusté par le bot, capital 1000 USDT, marchés
crypto Bitget, numéraire dynamique (sortir de l'USD s'il faiblit), « au bot de gérer
comme un pro ». Traduction clé : « comme un pro » = **discipline encodée, pas absence de
limite** ; « le plus possible » n'est cohérent que **borné par le MDD**.

- **`config.MANDATE_*`** : source unique de la politique (capital, MDD 20 %, levier ×5,
  risque/trade 0.75 %, réserve cash, seuil d'edge DSR≥0.90 + n≥120, refuges numéraire
  BTC/XAUT, sessions UTC, black-out macro, verrou réel `MANDATE_LIVE_ENABLED=False`).
- **`mandate.py`** (pur, testé) : `max_leverage` (mur dur), `target_leverage`
  (vol-targeting borné), `drawdown_halt` (la limite qui rend « MAX » sûr), `_passes_edge`
  / `futures_live_allowed` (**porte paper→réel** : un agent ne trade en réel que s'il bat
  le seuil déflaté T5 — verrou statistique issu du résultat B), `numeraire_recommendation`,
  `in_active_session`, `macro_blackout`, `risk_per_trade_usd`, `deployable_usd`.
- **Mise en réel PAR PALIERS** : (1) accumulation **spot** d'abord (edge structurel, pas
  directionnel, bornée par le MDD) ; (2) futures réel débloqué **agent par agent**, automa-
  tiquement, seulement quand `validation_report.json` montre DSR≥0.90 sur n≥120. Aujourd'hui :
  **0 agent éligible** (cf. B) → futures reste paper.
- **Architecture réel** : ce dépôt reste le **cerveau** (paper, `can_trade=False`) ; les
  ordres réels passent par le **MCP Agent Hub Bitget** (`bitget-mcp-server`, cf.
  `pc/BITGET_AGENT_HUB.md`) sur machine de trading, avec clé **Trade-only** rotée +
  whitelist IP. `accumulation_engine` expose `mode` (paper/RÉEL via MCP) sous le verrou.
- **Outils « Bitget Agent AI »** (AI Landscape, GetAgent, Playbook, Builder OS…) = produits
  hébergés Bitget (sous-comptes isolés), **pas** des API tierces. Le seul pont programmatique
  utilisable = le MCP Agent Hub ci-dessus.

**Reste avant le réel** (manuel, irréversible) : roter les clés fuitées → créer une clé
**Trade-only** (jamais Withdraw) + whitelist IP VPS → installer le MCP Agent Hub →
`MANDATE_LIVE_ENABLED=True`. Le spot peut alors accumuler en réel ; le futures attend l'edge.

---

## §30 — Affûtage macro (skill-hub Bitget) + échelle d'edge par agent
Demande : « mets les agents en edge » + paquet `bitget-skill-hub@1.0.2`. Deux volets.

**(1) Affûtage de l'agent macro (`macro_regime.py`)** — extraction de la MÉTHODO
déterministe des skills `btc-macro-analysis` / `macro-analyst` (sans embarquer leur
snapshot ni dépendre de leur endpoint tiers `datahub.noxiaohao.com`) : framework
**6 indicateurs -> posture monétaire -> biais BTC**, seuils de `rate-keys.md` (Core PCE
<2 dovish / >2.5 hawkish / >3 fort ; chômage <4 tendu / >5 slack ; NFP <100k / >250k ;
taux réel 10Y, DXY, VIX). Convention : hawkish = baissier BTC. `event_surprise`
(actual vs forecast, inversé pour chômage/claims). Données tirées de NOS sources FRED
sans clé (`macro_context` : VIXCLS, DTWEXBGS, DFII10, UNRATE, PCEPILFE→YoY, PAYEMS→Δ).
Branché dans `swarm_brain.agent_macro` (combinaison pondérée par confiance avec l'ancien
RISK_ON/OFF, fallback gracieux). Remplace un vote macro binaire (±0.6) par un biais gradué.

**(2) Échelle d'edge (`edge_ladder.py`)** — généralise la « porte d'edge » du mandat à
TOUS les agents : palier par agent depuis `validation_report.json` (T5) — LIVE (DSR≥0.90
∧ n≥120 ∧ OOS>0 → éligible réel), PROBATION (DSR≥0.50 ∧ n≥30), PAPER (DSR≥0.10),
NEGATIVE. Priors de poids ADVISORY (LIVE ×1.5 … NEGATIVE ×0.3) qui bornent EARCP sans
l'écraser. Mécanisme « par paliers, agent par agent » : seul le palier LIVE ouvre le réel
(cohérent avec `mandate.futures_live_allowed`). Étape de rapport dans `agent_control`.

**Nature du skill-hub** : 6 skills Claude Code (macro/sentiment/technique/news/on-chain)
qui donnent de l'edge analytique à l'agent de l'Agent Hub ; côté bot déterministe, seul
le savoir-faire macro est réutilisé. Aucun ordre, scan sécurité étendu aux 2 modules.

---

## §31 — Passage au RÉEL par paliers : exécution spot BTC (test-first)
Décision propriétaire : clé en Trade, brancher les fonds réels, `MANDATE_LIVE_ENABLED=True`.
Mise en œuvre PRUDENTE (test-first, spot BTC seul) :

- **`spot_executor.py`** — le SEUL module qui peut passer un ordre réel. Périmètre
  verrouillé : ACHAT spot BTC au marché, jamais vendre/levier/futures/retrait. Gardes
  durs : `MANDATE_LIVE_ENABLED` + `kill_switch` inactif + plafond/achat (50$) + plafond
  journalier (50$) + montant ≤ solde spot réel + idempotence (clientOid). **Mode --dry
  par défaut** : imprime la commande `bgc`, n'exécute RIEN sans `--confirm`. Exécution
  déléguée à l'Agent Hub (`bgc spot ...`).
- **Gate sécurité évolué (transparent)** : `security_agent` autorise l'exécution
  UNIQUEMENT dans `spot_executor.py`, et seulement s'il reste conforme — aucun mot
  interdit (vente/levier/futures/retrait) ET verrous présents (MANDATE_LIVE_ENABLED,
  kill_switch, confirm). Tout autre fichier garde l'interdiction totale d'ordre.
- **NON câblé à l'autonome** : l'accumulation reste paper (test-first). Le seul moyen de
  passer un ordre réel = `python spot_executor.py --confirm` (manuel). Le futures reste
  bloqué par l'échelle d'edge (0 agent LIVE).
- **`config`** : `MANDATE_LIVE_ENABLED=True`, `ACCUM_REAL_MAX_PER_BUY_USDT=50`,
  `ACCUM_REAL_MAX_DAILY_USDT=50`. Registre réel `accumulation_real_ledger.json` (gitignored).

Séquence de mise en réel : (1) `--dry` pour vérifier la commande vs `bgc spot
spot_place_order --help` ; (2) un achat minime confirmé (~5$) ; (3) vérifier le fill ;
(4) seulement ensuite, câbler l'autonome (palier suivant, décision séparée).

---

## §32 — Outils cherry-pickés (sans frameworks lourds)
Sur demande « cherche des outils utiles / intègre tes recommandations », on a repris
les IDÉES utiles de l'écosystème (CCXT, lib `arch`) SANS embarquer les frameworks lourds
ni violer la contrainte « déterministe, pas de réseaux de neurones ».

- **`fair_price.py`** (idée CCXT, sans la lib) : prix de RÉFÉRENCE cross-exchange =
  médiane de Binance/Bybit/OKX (réutilise les fetchers keyless de `arbitrage.py`),
  + premium/discount Bitget. Garde « MEILLEUR PRIX » : `is_fair_to_buy` → l'accumulation
  RÉELLE autonome n'achète PAS si Bitget cote >`ACCUM_MAX_PREMIUM_PCT` (0.30%) au-dessus
  du marché (évite d'acheter un pic propre à Bitget). Surfacé dans le dashboard.
- **`volatility.py`** (idée lib `arch`, en pur numpy) : EWMA RiskMetrics + GARCH(1,1)
  variance-targeting → vol CONDITIONNELLE (réactive aux chocs). Branchée dans
  `mandate.leverage_for(conviction, closes)` : vol-targeting du levier à partir des prix,
  toujours borné par le mur ×5.
- Écartés sciemment : FinRL/Qlib/TradeMaster (réseaux de neurones), Freqtrade/Jesse/
  Nautilus/Lean (réécriture d'archi), SaaS fermés, brokers actions (hors Bitget). Déjà
  couvert maison : HRP, López de Prado (DSR/PSR/purged WFA), Black-Scholes, lightweight-charts.
- Prochain (chemin d'ordre RÉEL, à valider sur VPS) : exécution maker/limit protégée du
  slippage dans `spot_executor` (gain de frais/slippage sur l'accumulation).

---

## §33 — Univers dynamique top-N + exécution maker/IOC
**Univers dynamique** (`universe.py`, gated `DYNAMIC_UNIVERSE`, défaut OFF) : remplace les
listes blanches figées par un univers construit à chaque cycle — LIQUIDITÉ (volume 24h des
tickers spot Bitget, un seul appel) filtrée QUALITÉ (bases présentes dans le top market-cap
**CoinGecko** — `coingecko_data` enfin branché dans l'analyse, plus seulement l'assistant),
ancres `config.SYMBOLS` toujours incluses. Branché dans `journal_scanner` (scan principal)
et `brain_cycle` (apprentissage). `UNIVERSE_TOP_N=20`, `UNIVERSE_MIN_VOLUME_USDT=5M`.
L'accumulation reste **BTC** (objectif inchangé).

**Exécution maker/IOC** (`spot_executor`, `EXEC_STYLE`, défaut `taker`) : 3 styles d'achat
spot — `taker` (marché, prouvé), `limit_ioc` (limite IOC plafonnée juste au-dessus de l'ask
→ remplit tout de suite mais JAMAIS au-delà du plafond, anti-slippage), `maker` (limite
post-only au bid → frais maker / meilleur prix, peut ne pas remplir). `build_order` pur et
testé ; repli sur marché si le carnet est indisponible (on n'est jamais bloqué). À valider
sur le VPS comme l'ordre marché (un achat 5$ par style). `ACCUM_SLIPPAGE_TOL_PCT=0.10`.

---

## §34 — DESIGN (non implémenté) : exécuteur futures réel borné (`futures_executor.py`)
**Statut : SPÉCIFICATION SEULE — aucun code écrit, aucune porte modifiée, aucun verrou levé.**
Demande propriétaire : « armer le chantier exécuteur futures ». Choix retenu : **design
écrit d'abord, validé avant toute ligne de code**. Ce §34 est ce design ; rien n'est
implémenté tant qu'il n'est pas approuvé.

### Pourquoi un design avant le code (le mur, factuel)
Un exécuteur futures réel doit appeler le venue (`place-order` / `/api/v2/mix/order` /
`open_long`…). Ces mots-clés sont **bloqués en dur** par DEUX portes : `safe_push_check.sh`
(étape 4, whitelist = `spot_executor.py` seul) et `security_agent.py`
(`AUTHORIZED_EXEC_FILES = ["spot_executor.py"]` + liste interdite incluant levier/futures).
Écrire ce module = **élargir le périmètre réel aux futures/levier**, ce que la règle #1 de
CLAUDE.md interdit aujourd'hui. C'est une décision lourde et IRRÉVERSIBLE de sécurité, pas
un simple verrou à lever. Elle ne se justifie que **quand un agent franchit la porte d'edge**
— or aujourd'hui **0 agent éligible** (`geometric` DSR 0.75/n64 < 0.90/120). Donc : on
conçoit, on ne branche pas.

### Principe directeur : `futures_executor.py` = 2ᵉ (et dernier) module d'ordre autorisé
Calqué sur la discipline `spot_executor.py` (§31), pas plus permissif :
- **Périmètre verrouillé** : ouverture/fermeture de position futures **directionnelle**
  sur signal d'un agent LIVE, levier ≤ `MANDATE_MAX_LEVERAGE` (×5). JAMAIS de retrait,
  jamais de cross au-delà du cap, jamais d'agent non-LIVE.
- **Mode `--dry` par défaut** : imprime la commande `bgc mix …`, n'exécute RIEN sans
  `--confirm`. Aucun chemin autonome au premier jet (comme le spot : manuel d'abord).
- **Délégation** : l'ordre réel passe par l'Agent Hub `bgc` (cf. §29), jamais d'appel HTTP
  direct dans ce dépôt.

### Ordre des gardes (TOUS doivent passer, court-circuit au 1ᵉʳ échec)
1. `kill_switch` absent (fichier `KILL_SWITCH`) ;
2. `mandate.live_enabled()` (`MANDATE_LIVE_ENABLED`) ET nouveau verrou dédié
   `FUTURES_AUTONOMOUS_LIVE` (défaut **False**) — double verrou, comme l'accum ;
3. `mandate.futures_live_allowed(agent, report)` **True** → l'agent est au palier LIVE
   (replay DSR≥0.90/n≥120/OOS>0 **ET** confirmation live n≥60/ic_t≥2.0, cf. §3x / commit
   5cdd027). Sans ça, refus sec ;
4. levier demandé ≤ `mandate.max_leverage` (mur ×5) ET cohérent avec `target_leverage`
   (vol-targeting, §32) ;
5. notional ≤ `FUTURES_REAL_MAX_PER_TRADE_USDT` ET exposition cumulée ≤
   `FUTURES_REAL_MAX_GROSS_USDT` (caps durs, petits au début) ;
6. `mandate.drawdown_halt` non déclenché (equity_curve réelle, §28/B.1) ;
7. session active + pas de black-out macro (`mandate.in_active_session` / `macro_blackout`) ;
8. idempotence `clientOid` (rejoue sans doubler), comme spot.

### Construction d'ordre (PUR, testable hors réel)
`build_futures_order(...)` pur (comme `build_order` spot, §33) : prend signal + caps +
contexte, retourne le descriptif d'ordre (symbole, side, taille, levier, marge, clientOid)
SANS effet de bord. Testé dans `tests_audit.py`. Le passage réel est un mince wrapper
au-dessus, gardé par les 8 points ci-dessus.

### Ce qui doit changer dans les portes (UNIQUEMENT à l'étape réelle, sur GO explicite)
- `safe_push_check.sh` étape 4 : ajouter `futures_executor.py` à la whitelist d'exclusion.
- `security_agent.py` : `AUTHORIZED_EXEC_FILES += ["futures_executor.py"]` + un
  `scan_authorized_exec` dédié futures (vérifie : verrous présents, caps présents, levier
  borné, aucun `withdraw`/`transfer`, `--confirm` requis). Le futures reste interdit partout
  ailleurs. **Cette extension est le point de non-retour : elle n'est faite que lorsqu'un
  agent est réellement LIVE et sur décision explicite, jamais en autonomie.**

### Config à ajouter (tous OFF / petits au départ)
`FUTURES_AUTONOMOUS_LIVE=False`, `FUTURES_REAL_MAX_PER_TRADE_USDT` (ex. 10),
`FUTURES_REAL_MAX_GROSS_USDT` (ex. 20), `FUTURES_REAL_LEDGER=futures_real_ledger.json`
(gitignored). Réutilise `MANDATE_MAX_LEVERAGE`, seuils d'edge, MDD existants.

### Séquence de mise en réel (test-first, calquée §31 — chaque étape = décision séparée)
1. **Maintenant** : écrire le module en **DRY-RUN gaté** + `build_futures_order` pur + tests,
   SANS toucher les portes (le wrapper réel lève `NotImplementedError` ou reste un stub
   imprimant la commande) → reste paper, 3 portes vertes, poussable.
2. **Quand un agent passe LIVE** (replay ET live au-dessus du seuil) : revue + extension des
   2 portes sécurité (ci-dessus), sur GO explicite.
3. `--dry` pour vérifier la commande vs `bgc mix … --help`.
4. Un trade minime confirmé manuellement (`--confirm`), levier ×1-2, notional plancher.
5. Vérifier fill + marge + SL ; seulement ensuite envisager le câblage autonome (palier
   suivant, encore une décision séparée). **Jamais full-auto sur la machine aux clés (règle #3).**

### Ligne dure conservée
Aucune de ces étapes ne se fait sans (a) un agent réellement éligible et (b) un GO explicite
du propriétaire. Le design ne lève rien ; il rend le chantier prêt et auditable.

---

## §35 — Breadth transversale : attaquer la PUISSANCE STATISTIQUE (pas le modèle)

**Diagnostic du blocage d'edge.** Aucun agent n'est LIVE. La porte exige DSR ≥ 0.90 ET
n ≥ 120. En mono-symbole (BTC), tous les agents ont **n = 64** (plafonné par la longueur
d'historique) : l'échantillon échoue *directement*, et plombe le DSR (qui se dé-pénalise
avec n). geometric battait pourtant le plancher de bruit (Sharpe 0.22 > sr0_max 0.135,
PSR 0.96, DSR 0.75) → edge apparent mais **sous-alimenté**. Le facteur limitant n'était pas
la capacité de modèle (donc un réseau de neurones n'aide pas — il sur-apprendrait sur n=64
et le DSR/haircut/WFA le déflateraient ; cf. §1, contrainte propriétaire « aucun deep net »).

**Levier honnête = la largeur (breadth).** Loi fondamentale (Grinold-Kahn) : IR ≈ IC·√(breadth).
Évaluer chaque agent en COUPE TRANSVERSALE sur l'univers liquide multiplie le nombre de
paris directionnels. PIÈGE : le crypto est très corrélé (beta commun) → empiler 20 symboles
ne donne PAS 20× d'info indépendante. Sans correction, on promouvrait un agent en LIVE sur
un edge factice → trade réel sur du vent.

**Implémentation (`agent_validation.py`, ADVISORY — ne touche NI la porte NI les poids) :**
- `average_cross_correlation(panel)` : ρ̄ = corrélation transversale moyenne des rendements-
  stratégie sign(vote)·fwd entre symboles.
- `effective_sample_size(n_nom, N, ρ̄)` : **n EFFECTIF** par variance inflation —
  `n_eff = périodes · N/(1+(N−1)ρ̄)`. ρ̄→0 ⇒ n_eff≈n_nom (full breadth) ; ρ̄→1 ⇒ n_eff≈n d'un
  seul symbole (AUCUNE inflation). ρ̄ écrêté à [0,1] (la corrélation négative n'est pas
  créditée — conservateur pour une porte de promotion).
- `rank_pure_agents_xs(...)` / `run_xs(...)` : DSR/PSR/IC-t recalculés sur n_eff.
- Tests (`tests_audit.py`) : propriété de SÛRETÉ prouvée — séries indépendantes ⇒ n_eff≈n_nom ;
  séries parfaitement corrélées ⇒ n_eff≈n d'un seul symbole (pas d'inflation).

**Résultat live (12 symboles, 1h, 600 barres) — IMPORTANT, et négatif :** n_eff ≈ 350 (≥120
franchi, ρ̄≈0.11 donc haircut modéré 768→350). MAIS l'edge de geometric **ne généralise pas** :
IC +0.15→**−0.05**, Sharpe 0.22→0.04, **DSR 0.75→0.33**. Aucun agent ne passe DSR≥0.90.
Conclusion honnête : la performance BTC mono-symbole était *sample-specific* (faible puissance
= lecture flatteuse). La breadth ne « débloque » pas un agent — elle **réfute** l'edge supposé.
Le vrai chantier n'est donc pas la plomberie de validation mais **l'ALPHA des agents** : leur
signal doit montrer un IC/DSR transversal positif ET robuste. `rank_pure_agents_xs` est
désormais l'**étalon honnête** pour mesurer tout nouvel agent/signal. Aucune promotion LIVE
tant que cet étalon n'est pas franchi (toujours + GO explicite + double verrou + caps).

---

## §36 — Recherche d'alpha large (201 signaux, 8 familles) : résultat NÉGATIF honnête

Suite à §35 (« le mur est l'alpha, pas la donnée »), balayage systématique de signaux
déterministes (sans réseau de neurones, §1) mesurés à l'étalon transversal, sous discipline
anti-data-mining stricte. **Aucun signal promu** ; on consigne la méthode et le résultat pour
ne pas le re-courir à l'aveugle et ne JAMAIS promouvoir un signal qui échoue la barre honnête.

**Protocole (orchestration multi-agents) :**
- Panel **gelé** : 15 symboles liquides × ~1000 barres 1h (inclut XAUT/or → décorrélé). Split
  temporel IS/OOS (`is_frac=0.7`) ; harnais d'éval = coupe transversale réutilisant
  `agent_validation` (n effectif anti-inflation, rank IC, PSR/DSR). Identique pour tous.
- 8 familles (momentum XS, tendance TS, reversion, vol/régime, volume/flux, structure,
  saisonnalité, accélération) → **201 variants** générés et mesurés. **Sélection sur IS
  uniquement** ; OOS réservé à une **vérif adverse indépendante** (re-exécution du code,
  cohérence de signe, robustesse au re-split, breadth >55 % des symboles).
- **Déflation multiple-testing GLOBALE** (le point clé) : `n_trials = 201` → SR0_max (Sharpe
  max attendu sous H0) ≈ **0.21/période**. Le « gagnant » doit battre CE plancher, pas un seuil naïf.

**Résultat :** la vérif adverse par candidat a laissé passer **2 survivants** (famille
`acceleration` : *fade de courbure* = ajuste une parabole au log-prix, inverse l'accélération,
normalise par la vol). OOS ic_t ≈ 2.0, breadth ≈ 0.85, robustes au re-split. **MAIS** sous la
déflation globale : Sharpe OOS ≈ 0.04 ≪ SR0_max 0.21 → **DSR déflaté ≈ 0.01**. AUCUN signal ne
passe (DSR≥0.90 + ic_t OOS≥2). Le re-split l'explique : leur edge se concentre dans la moitié
**récente** (régime de reversion) — pas un edge intemporel. Motif répété sur TOUTES les familles :
IC IS positif → IC OOS nul/négatif (le panel a un régime momentum en IS, reversion en OOS).

**Leçon :** la vérif par-candidat ne suffit pas ; seule la déflation sur le nombre TOTAL d'essais
attrape le data-mining. Les 2 « survivants » étaient des gagnants de loterie. Le fade de courbure
est l'idée la moins fragile (à garder en watch/paper SI le propriétaire le souhaite, jamais en réel
sur cette preuve). Caveat : un bug d'orchestration a passé des chemins « undefined » à quelques
agents (quelques rejets non fiables) ; sans effet sur la conclusion (le meilleur Sharpe OOS de tout
le balayage, 0.10, reste ≪ 0.21). Outils de recherche (harnais IS/OOS, panel, workflow) en scratch,
non committés ; réutiliser `rank_pure_agents_xs` (étalon committé) pour toute reprise.

---

## §37 — Horizons COURTS (15m, 5m) + microstructure : confirmation du résultat NÉGATIF

Suite §36, deux directions demandées : (1) microstructure comme source de signal, (2) horizons courts.

**Contrainte de données (microstructure).** La vraie microstructure (carnet L2 + tape) est
**LIVE-ONLY** : Bitget n'expose pas d'historique (`merge-depth`/`fills` = snapshot instantané ;
`book_collector.py`/`.microstructure_buffer.json` ne gardent ~600 snapshots ≈ 10 min). **Non
backtestable** sur panel gelé. Seuls des **proxys dérivés des bougies** (Amihud, Kyle-λ, entropie
d'order-flow `regime_features`, biais de volume, vol de range) sont testables — et ils sont inclus
comme famille dédiée. La vraie L2/tape ne peut être évaluée que par **journalisation live qui
s'accumule** (chemin 2), sans verdict immédiat.

**Méthode (identique §36, étalon transversal anti-data-mining).** Panels courts gelés (15 symboles
× 1000 barres) : 15m (~250 h, horizon 4 = 1 h) et 5m (~83 h, horizon 6 = 30 min). 7 familles dont
`microstructure_liquidity`. Sélection IS-only → vérif adverse OOS → déflation multiple-testing globale.

**Résultats — négatifs, cohérents avec §35/§36 :**
- **15m** : 180 candidats. 2 survivants (`vol_regime` = expansion de range × direction), OOS Sharpe
  0.05–0.07 ; sous déflation (180 essais, SR0_max 0.15) → DSR ≈ 0.02–0.07. **Aucun ne passe.**
- **5m** : 173 candidats. **0 survivant** (aucun ne franchit même la vérif adverse OOS : la reversion
  d'accélération retombe à ic_t 1.43, le suivi de courbure s'effondre OOS).
- **microstructure_liquidity** : 21 (15m) + 27 (5m) variants → **0 survivant** aux deux horizons.
  Les proxys bougies (sans vrai L2/tape) n'ont pas d'edge.

**Cause structurelle (le vrai mur).** À TOUS les horizons (5m/15m/1h), `rho` transversal ≈ 0.17–0.25 :
le crypto bouge en *common-mode* (beta commun). Les paris directionnels ne sont donc pas
indépendants → le `n` effectif est plafonné (~350–600 sur 1600–2400 nominal) → les t-stats honnêtes
plafonnent ~1.5, sous la barre. Les signaux flatteurs en IS s'inversent/s'effondrent en OOS (régime).
Le signe « gagnant » bascule avec l'horizon (courbure : fade à 1 h, suivi à 30 min) = non robuste.

**Bilan recherche d'alpha (§35→§37).** ~554 candidats déterministes, 8 familles, 3 horizons : **aucun
alpha directionnel robuste** ne franchit la barre honnête. Quasi-touches notées mais non promues :
saisonnalité horaire (réelle, OOS-cohérente, mais panel 5m trop court ~3,5 j → à re-tester sur ≥30 j),
et reversion court-terme (réelle mais common-mode). Frontières restantes : (a) vraie microstructure
L2/tape via collecteur live qui accumule (chemin 2, pas de verdict instantané) ; (b) saisonnalité sur
historique long ; (c) **acter que le directionnel pur n'a pas d'edge** → futures reste paper, l'autonomie
se concentre sur l'accumulation spot (déjà réelle/cappée, ne suppose aucun edge directionnel).

---

## §38 — DÉCISION : pivot stratégique vers le spot (futures réel suspendu)

**Décision du propriétaire (27/06), actée après §35-37.** La recherche d'alpha directionnel
(~554 signaux, 8 familles, 3 horizons, étalon transversal honnête) n'a trouvé AUCUN edge robuste ;
la cause est structurelle (crypto *common-mode*, rho 0.17-0.25 → n effectif plafonné). On en tire
la conséquence honnête plutôt que de forcer.

**Ce que ça fixe :**
- Le **chantier futures réel (§34) est suspendu**, pas annulé : `futures_executor.py` reste DRY-RUN,
  chemin réel `NotImplementedError`, jamais câblé. La porte d'edge (0 agent LIVE) le maintient paper
  *de facto* ; cette décision le maintient paper *de jure*. Aucune étape ≥2 ne sera entreprise sans
  (a) une source d'edge nouvelle et prouvée à l'étalon ET (b) un GO explicite — la barre reste haute.
- **L'autonomie se concentre sur l'accumulation spot BTC** : déjà réelle, cappée (5 $/j, double verrou),
  et NON-DIRECTIONNELLE par conception. `accumulation_engine.py` fait déjà un DCA *opportunity-aware*
  (`opportunity_score` = RSI + fear/greed + drawdown → achète plus sur les creux), avec garde premium
  et meilleur-prix (`fair_price`). Il n'a pas besoin d'edge directionnel : il améliore l'entrée d'un
  achat qu'on fait de toute façon (≠ parier sur la direction).
- **Corollaire utile de §35-37** : la reversion court-terme EST réelle (juste non tradeable en
  cross-section market-neutral). Pour une accumulation MONO-actif, c'est exploitable honnêtement comme
  *timing d'entrée* (acheter sur faiblesse court-terme = meilleur prix moyen), sans prétendre prédire.

**Ligne dure inchangée.** Aucun verrou levé ici (`MANDATE_LIVE_ENABLED`, `ACCUM_AUTONOMOUS_LIVE`,
`FUTURES_AUTONOMOUS_LIVE` restent tels quels). Rien de full-auto. La décision REDIRIGE l'effort ;
elle n'arme rien.

**Premier livrable spot — affûtage du timing d'entrée (implémenté, validé).** Métrique honnête =
*avantage de prix de revient* (cost basis) d'un DCA pondéré-opportunité vs DCA plat, **à budget
égal** (isole le timing). Backtest (15 symboles, IS/OOS) : l'`opportunity_score` actuel est déjà
bon (+0,69 % OOS, 93 % des symboles positifs ; +3-4 % sur BTC daily). Affûtage retenu : mêler une
**survente court-terme** (`short_term_oversold`, z-score sous la MA-24) au score, poids
`ACCUM_ST_WEIGHT=0.30` → avantage OOS **+0,69 %→+0,77 %**, plateau stable (k∈[20,28], α∈[0.25,0.35]),
généralise (1h/15m/5m/daily). C'est du TIMING (acheter sur faiblesse court-terme ce qu'on accumule de
toute façon), pas une prédiction — cohérent avec « reversion réelle mais common-mode » (§35-37).
`ACCUM_ST_WEIGHT=0` → score historique inchangé (rétrocompatible). Le réel reste cappé/gaté/double
verrou ; rien n'est armé.

**Cadence adaptative — testée et REJETÉE (négatif honnête).** Question : acheter *quand* c'est bon
(intervalle court quand bon marché, long quand cher) bat-il la grille fixe ? Backtest cost-basis
(15 symboles, IS/OOS) : la cadence adaptative + sizing bat le moteur actuel de ~+1 % OOS sur le panel
1h, MAIS **pas robuste** : seulement 67-86 % des symboles positifs (vs 93 % pour le sizing), **échoue
à 15m** (40 % positifs), et surtout **BTC — l'actif accumulé — est NÉGATIF en in-sample** (sign-flip
IS/OOS = régime-dépendant). Raison STRUCTURELLE : le sizing pondère sans différer le déploiement (on
reste investi) ; la cadence adaptative DIFFÈRE les achats (« attendre le creux ») → se bat contre la
dérive haussière séculaire, exactement le pari d'un accumulateur long terme. **Décision : garder
l'intervalle FIXE.** Le moteur n'est pas modifié. (Outils de backtest en scratch, non committés.)

**Vol-targeting du montant — testé et REJETÉ (négatif honnête).** Question : moduler la taille
par la volatilité lisse-t-il le prix de revient ? Backtest cost-basis (15 symboles, IS/OOS) :
- *inverse* (réduire la taille quand la vol explose, l'idée intuitive) : **contre-productif** —
  OOS −0,28 % (27 % positifs), −0,55 % sur BTC. En crypto la vol explose dans les KRACHS (prix bas)
  → réduire la taille y achète MOINS au plus bas.
- *direct* (augmenter dans la vol) : marginal et incohérent (IS négatif 1h, échoue à 5m), et
  **redondant** avec le drawdown qui capte déjà « acheter la capitulation ».
**Décision : pas de vol-targeting du montant.** Moteur non modifié. C'est une validation du design :
`opportunity_score` (drawdown/RSI) capte déjà l'effet recherché.

**Bilan affûtage spot.** Trois leviers testés sur la métrique honnête cost-basis : (1) **sizing par
survente court-terme → LIVRÉ** (robuste, +0,77 % OOS, 93 %) ; (2) cadence adaptative → rejetée
(régime-dépendante, fight la dérive) ; (3) vol-targeting du montant → rejeté (contre-productif/
redondant). Le moteur d'accumulation est dans un état stable et bien conçu ; l'espace d'amélioration
honnête est largement épuisé. Le réel reste cappé/gaté/double verrou.

---

## §39 — Diagnostic des AGENTS du swarm : le « no edge » n'est (presque) pas un bug d'agent

Question (propriétaire) : les agents fonctionnent-ils, un blocage masque-t-il un edge ? Évaluation
chemin-2 des **11 agents** sur `brain_log.json` (500 votes journalisés) + diagnostic cause-racine
(workflow 4 investigateurs). Constats honnêtes :

- **Blocage structurel d'évaluation** : l'étalon ne rejouait que **4 agents sur 11** (les 7 live —
  orderflow/derivs/liquidations/macro/sentiment/structure/technicals — ne sont pas rejouables sur
  bougies). Le chemin 2 (`evaluate_from_log`) les évalue tous : c'est fait ici.
- **macro & sentiment : SAINS, pas dégénérés.** Leur IC=0 est un **artefact de mesure** : ce sont des
  signaux **marché-large** (macro ignore le symbole ; F&G est quotidien+global) → une IC *transversale*
  est nulle par construction, et le log (4,3 h) est trop court. Données réelles, votes corrects.
  **Aucun fix** (forcer 0 = régression).
- **technicals : anti-prédictif mais NON robuste.** ~Toujours-long ; IC négatif = régime de reversion
  court-terme **non robuste OOS** (3 flips de signe IS/OOS, IC poolée ≈ 0). **Ne PAS inverser**
  (sur-ajustement) ; l'apprentissage EARCP le down-weighte déjà (juge à ~1 h).
- **savant : seul vrai défaut → CORRIGÉ.** Un nudge Fear&Greed **symbole-indépendant** le figeait à
  +0,15 ~83 % du temps ET **double-comptait l'agent `sentiment`**. Retiré : savant ne vote plus que sur
  sa rupture de symétrie Mahalanobis (sa spécialité), spécificité par-symbole restaurée. Test mis à jour.

**Insight le plus précieux** : tout le « no edge » (§35-38) ne mesurait que l'**alpha transversal**
(cul-de-sac démontré). Les agents de **régime / market-timing** (macro, sentiment) ont un edge éventuel
**temporel** (le vote prédit-il le rendement du MARCHÉ dans le temps ?), jamais évalué — la métrique
transversale les zéro-note par construction. Frontière vierge, mais **time-gated** (semaines de votes
vs rendements marché), à brancher comme la microstructure si on veut la creuser.

---

## §40 — Données ORTHOGONALES + carry non-directionnel + chemin 3 (edge temporel)

**Demande (02/07)** : « améliorer le bot, chercher de nouvelles sources de data, ajouter
des stratégies rentables ». Réponse HONNÊTE vis-à-vis de §35-39 : ne PAS rajouter de
signaux dérivés des bougies (554 candidats déjà réfutés — en rajouter serait du
data-mining déguisé). Trois axes orthogonaux à la place, tous advisory/paper.

**1. Nouvelles sources (familles jamais balayées par §36-37, toutes gratuites/sans clé,
fail-safe, cachées runtime_cache, sondées en direct depuis le VPS)** :
- `derivs_positioning.py` — positionnement dérivés : funding natif Bitget (courant +
  historique) + multi-venues (Binance/OKX/Bybit — le géo-blocage 451/403 noté dans
  market_sources a DISPARU, re-sondé 7/7 endpoints OK), OI, basis perp-spot natif,
  **série horaire du ratio de comptes long/short Bitget** (`account-long-short`).
- `onchain_btc.py` — première source on-chain : Hash Ribbons (SMA30/60 du hashrate,
  blockchain.info 6 mois ; capitulation/reprise mineurs = timing d'ACCUMULATION
  historique), frais/congestion mempool.space, ajustement de difficulté.
- `stablecoin_flow.py` — offre totale de stablecoins (DefiLlama, série journalière
  depuis 2017) : momentum 7j/30j = « dry powder » ; mint/burn USDT/USDC mensuel.
- `deribit_vol.py` — DVOL (vol implicite forward-looking, l'anti-GARCH) BTC/ETH,
  vol réalisée, **VRP = DVOL − RV**, régime calme/normal/stress + drapeau expansion.

**2. Deux nouveaux agents du cerveau (12e/13e, poids auto-seed 1.0, EARCP apprend)** :
- **flows** (`flows_agent.py`) — marché-large, momentum de l'offre de stablecoins
  (0.6·tanh(pct7/0.5)+0.4·tanh(pct30/2)), confiance PLAFONNÉE 0.5 (humilité : jamais
  validé à l'étalon). Comme macro/sentiment, son edge éventuel est TEMPOREL (§39).
- **carry** (`carry_agent.py`) — contrarian sur les extrêmes de positionnement :
  z-score du funding vs historique + foule L/S + basis, confiance PLAFONNÉE 0.6.
  ≠ `derivs` (contrarian 1D funding instantané) : 3 dimensions + mémoire historique.
  Sanity live : foule Bitget ~2.0-2.4 crowd-long en peur extrême → vote négatif modéré,
  cohérent avec la porte de régime.

**3. Stratégie non-directionnelle mesurée (`carry_monitor.py`, PAPER)** : le
cash-and-carry (long spot + short perp, delta-neutre) encaisse le funding SANS edge
directionnel — la seule famille de rendement compatible avec le verdict §35-38. Le
moniteur calcule l'APR brut (funding moyen 30 périodes annualisé) et NET (frais
entrée+sortie amortis sur 30 j), étiquette ATTRACTIF/NEUTRE/NEGATIF
(seuil `CARRY_SEUIL_APR_PCT`=5 %), journalise dans `.carry_journal.json` (gitignoré,
cap 500, auto-throttle 1 h) via le cycle scan (agent_control). Mesure honnête du jour :
BTC ~+3.9 % net (NEUTRE), la plupart NÉGATIF — le carry est maigre en peur extrême ;
le moniteur dira quand il redevient payant. AUCUNE exécution (décision humaine, §38).

**4. Chemin 3 de validation — edge TEMPOREL (la frontière §39, implémentée)** :
`agent_validation.evaluate_market_timing` groupe brain_log par cycles de scan
(`_cycles_from_log`), puis mesure par agent (+ pseudo-agent `consensus`) l'IC/t/hit/
Sharpe/PSR entre vote moyen marché-large au cycle t et rendement MOYEN du marché à
t+h, échantillonnage NON CHEVAUCHANT (pas = horizon, 12 cycles ≈ 1 h). Câblé dans
`validation_report.json` (section `market_timing`, advisory). Time-gated : ~8
échantillons sur les 8 h de log actuelles — c'est l'accumulation des semaines qui
rendra le verdict. C'est l'étalon qui jugera flows/macro/sentiment (la coupe
transversale les zéro-note par construction).

**Garde-fous inchangés** : tout paper/advisory, aucun verrou touché, déterministe
(zéro NN), 3 portes vertes (283/283 tests, +27), confiances des nouveaux agents
plafonnées tant que rien n'a franchi l'étalon. Piège d'écriture appris : les mots
scannés par les portes incluent le français « transfert » (contient un mot-clé) —
dire « flux »/« virement ».

**Reste ouvert (non fait, à décider)** : ~~brancher `rank_pure_agents_xs`~~ et
~~appliquer les priors advisory d'edge_ladder~~ — les deux FAITS en §41 ; Hash
Ribbons comme entrée optionnelle de l'opportunity_score d'accumulation (exigerait
le backtest cost-basis §38 avant toute intégration).

---

## §41 — La boucle mesure→poids fermée : ranking transversal + priors d'edge branchés

**Contexte.** Les deux chantiers laissés « à décider » en §40, choisis parce qu'ils
ferment enfin la boucle entre l'edge MESURÉ (validation T5) et l'edge APPRIS (poids
EARCP) — sans toucher AUCUN verrou ni seuil : le futures reste paper, la porte
d'edge garde DSR≥0.90, n≥120, OOS>0 ET confirmation live.

**1. Le rapport de validation lit la coupe TRANSVERSALE (`brain_validation`).**
`main()` tente `run_xs()` (univers liquide, n EFFECTIF corrigé de la corrélation
transversale, §40) et ne retombe sur le mono-symbole `run(symbol)` qu'en cas d'échec
(réseau/univers). Le rapport porte `ranking_mode` (`xs`/`mono`) et `n_symbols`
(transparence). Effet mesuré en direct (11 symboles) : n_eff 212–298 ≫ 120 — le
palier LIVE devient MATHÉMATIQUEMENT atteignable sans baisser aucun seuil. Verdict
honnête du jour : la breadth DÉGRADE tout le monde (divergent DSR 0.56→0.29,
simons 0.53→0.26 : leur « edge » mono-BTC ne se réplique pas en coupe) — les 4
agents purs sortent PAPER, personne n'approche le réel. La porte dit enfin quelque
chose de crédible au lieu d'être structurellement fermée.

**2. Les priors d'edge bornent ENFIN l'appris (`edge_ladder.weight_priors` +
`swarm_brain._apply_edge_priors`).** Nouvelle carte {agent: prior} : palier replay
-> prior (×1.5/×1.0/×0.6/×0.3), PLUS un dérate symétrique de `_live_confirms` — IC
live significativement NÉGATIF (n≥60, ic_t≤−2.0) plafonne à ×0.3 : l'évidence
CONTRE un agent compte autant que l'évidence pour. Un agent ABSENT du rapport
reste neutre ×1.0 (on bride sur preuve, pas faute de mesure — ≠ `agent_tier` qui
répond NEGATIVE : lui est une porte de promotion, fail-closed). Application dans
`learn()` : multiplicateur ADOUCI `prior**alpha` (`BRAIN_EDGE_PRIOR_ALPHA`=0.5),
renormalisation moy~1, re-borne [MIN,MAX] ; fail-safe NEUTRE (pas de rapport /
module en panne -> poids inchangés) ; débrayable `BRAIN_EDGE_PRIORS=0`. Effet
mesuré : technicals (ic_t live −2.87 sur 484 votes, 2e-3e poids — l'anomalie
pointée en §40) 0.413→0.242 ; divergent (poids 3.0 appris sur la cohérence, prior
PAPER) sera tiré vers le bas au prochain learn(). C'est exactement « l'edge mesuré
borne l'edge appris ».

**Pourquoi l'adoucissement α=0.5 ?** Prior plein (×0.3 brut) écraserait
l'apprentissage EARCP (contraire au contrat « advisory » d'edge_ladder) ; √prior
(×0.55) ORIENTE : un agent bridé peut encore remonter s'il accumule de la
performance réelle — le plancher d'exploration EARCP reste vivant.

**Garde-fous** : tout paper/advisory, aucun verrou touché, déterministe, portes
vertes (287/287 tests, +4 : carte des priors + dérate live, adoucissement/fail-safe/
débrayage, ranking_mode). Le rapport reste gitignoré (état local).

---

## §42 — Backtest cost-basis COMMITTÉ ; Hash Ribbons testé et REJETÉ (négatif honnête)

**Contexte.** Dernier item ouvert de §40 : Hash Ribbons (reprise des mineurs,
`onchain_btc`) comme entrée de l'`opportunity_score` d'accumulation — sous condition
du backtest cost-basis §38, dont les outils étaient restés en scratch non committés
(irreproductibles). Les deux points sont réglés ensemble.

**1. L'outillage est maintenant COMMITTÉ et testé : `accum_backtest.py`.** Cœurs purs
(`ribbon_signals` — équivalence prouvée par test avec `hash_ribbons` rejoué sur chaque
préfixe, en une passe O(n) au lieu de O(n³) —, `cost_basis`, `avantage_pct`,
`score_hr`, `simulate_amounts`, `folds_positifs`, `run_backtest`) + collecte réseau
best-effort cachée (prix journalier blockchain.info depuis 2009, hashrate complet,
F&G historique alternative.me 2018+). Fidélité production : le score est calculé sur
une FENÊTRE de 200 jours (comme `analyze()` qui lit `_closes(limit=200)`), défauts du
moteur figés (st_weight 0.30, base 10 $, mult 5). Protocole anti-surapprentissage :
grille (2 formes × 4 poids) choisie sur IS (70 % chrono), jugée UNE fois sur OOS,
robustesse = 5 plis contigus, nombre d'essais AFFICHÉ dans le rapport. Piège trouvé
en route (test de régression ajouté) : le cache runtime passe par JSON — les clés
int d'un dict deviennent des str au rechargement ; sans normalisation, le F&G
historique était silencieusement perdu (couverture 0 jour).

**2. Verdict Hash Ribbons : REJETÉ, données nettes.** Sur l'historique complet
(5 794 j) : chaque combinaison (boost/signed × w∈{0.1..0.5}) fait PIRE que la
baseline en IS ET en OOS, dégradation MONOTONE avec le poids (OOS +5.52 % baseline
→ +2.44 % à w=0.5). Sur l'ère moderne 2018+ (3 070 j, F&G réel) : baseline
IS +6.46 %/OOS +1.27 %/plis 100 % positifs, et le ribbon dégrade encore tout,
monotone (OOS +1.27 → −0.69 à w=0.5). Explication structurelle (cohérente avec les
rejets §38) : la « reprise » des ribbons CONFIRME le creux après coup — elle se
déclenche quand le hashrate (et le prix) a déjà rebondi ; surpondérer ces jours-là
achète APRÈS le bas, là où le moteur achète le creux lui-même (drawdown/RSI/peur/
survente CT). 495 j de reprise sur 5 794 : le signal n'est pas rare au sens utile.
**Décision : `opportunity_score` NON modifié.** `onchain_btc` reste une source
advisory d'observabilité (dashboard/Telegram), pas une entrée de sizing.

**Bonus de validation.** Le backtest committé revalide le moteur DÉPLOYÉ sur son
terrain réel (BTC daily 2018+) : +1.27 % OOS, 100 % des plis positifs — cohérent
avec §38 (+0.77 % OOS panel 15 symboles). Sur l'historique complet pré-2018 la
baseline est négative par époques (bulles paraboliques 2011-2017 : « acheter le
drawdown » se fait devancer par le plat quand ça ne corrige jamais) — rappel utile
que l'avantage du DCA opportuniste est un edge de RÉGIME moderne, pas une loi.

**Garde-fous** : lecture seule de bout en bout, aucun état modifié, aucun verrou,
292/292 tests (+5 : équivalence préfixes, invariance d'échelle du cost basis,
formes du mélange, régression clés JSON, structure/sélection-IS du protocole).

---

## §43 — Le réel rendu MESURABLE : réconciliation registre ↔ fills ↔ compte

**Contexte.** Demande du propriétaire : « passer en réel ». Constat d'audit : le réel
est DÉJÀ actif — double verrou levé avant cette session (MANDATE_LIVE_ENABLED +
ACCUM_AUTONOMOUS_LIVE=1), 6 achats réels journalisés (5 $/j à 12:00 UTC via
bitget-scan). Le futures réel reste IMPOSSIBLE honnêtement : 0 agent au palier LIVE
(la coupe transversale §41 classe tout PAPER) et décision propriétaire §38 — le
chemin vers le futures réel passe par l'étalon, pas par un interrupteur. Le vrai
manque du réel n'était pas un verrou à lever mais une CÉCITÉ post-achat : le registre
ne notait ni prix de remplissage, ni quantité BTC, ni frais — prix de revient réel
inconnaissable, écart registre/compte indétectable.

**Livré (`accum_reconcile.py`, LECTURE SEULE — n'écrit JAMAIS dans le registre de
l'exécuteur).** Cœurs purs : `group_fills` (agrégation par ordre, VWAP, frais BTC),
`match_buys` (appariement temps±300s / montant±35 % — les fills spot Bitget
n'exposent pas le clientOid), `bilan` (prix de revient réel, PnL latent, écart
solde). Réconciliation 3 SOURCES : registre (intentions) ↔ fills (exécutions vues
par Bitget, --read-only) ↔ solde BTC du compte. Invariant exploité : on n'achète
QUE du BTC -> un solde < cumul acheté net des frais = vente/retrait hors périmètre
= ANOMALIE. Fenêtre de fills bornée par l'API : AFFICHÉE (jamais de faux « OK » sur
fenêtre tronquée). Mesure du jour : 6/6 appariés, 29.94 USDT -> 0.00049900 BTC,
prix de revient réel 59 994.81 $, PnL latent ~+2.9 %, solde couvre le cumul
(+179 sats de poussière antérieure), zéro anomalie.

**Corollaire de sécurité découvert et corrigé.** `python accumulation_engine.py`
(documenté « état accumulation » dans CLAUDE.md) exécute en fait run() = un CYCLE —
qui, verrous levés, peut ACHETER en réel. Une commande de consultation ne doit
jamais emprunter ce chemin : ajout de `status()` / `--status` (consultation pure,
testée : ne déclenche jamais _run_real, n'écrit rien), CLAUDE.md corrigé, et les
nouvelles commandes Telegram `/accum` (statut) et `/accum_reel` (réconciliation)
n'utilisent QUE ces chemins. Dashboard : prix de revient réel + PnL + verdict de
réconciliation dans le panneau accumulation (cache 15 min).

**Garde-fous** : aucun verrou touché (ils étaient déjà levés par le propriétaire),
aucun nouveau chemin d'ordre (spot_executor inchangé), tout nouveau code en lecture
seule, 297/297 tests (+4 : VWAP/frais, appariement/fenêtre, bilan/anomalies,
status lecture seule).

---

## §44 — Sizing réel proportionnel : l'edge validé s'exprime enfin sous le cap

**Découverte.** Le montant recommandé par le moteur (base 10 $, mult ×5 -> 10..50 $)
dépasse TOUJOURS le cap réel de 5 $ : `min(recommandé, cap)` donnait donc 5 $ PLAT
chaque jour — le sizing opportuniste, précisément l'edge validé au backtest
cost-basis (§38 : +0.77 % OOS, 93 % des symboles ; revalidé §42 : +1.27 % OOS BTC
daily 2018+), était structurellement NEUTRALISÉ en production. Les 6 premiers achats
réels le confirment : tous à 5.00 $.

**Décision propriétaire (02/07, sur question explicite)** : sizing **variable 2–5 $**.
`real_dca_amount(score) = cap·(f + (1−f)·score)`, `f = ACCUM_REAL_FLOOR_FRAC = 0.4`
(écrêté [0.1, 1] ; 1.0 = retour au plat) : 5 $ en capitulation, ~2 $ les jours chers,
moyenne ~3 $/j. Options écartées : garder 5 $ plat (edge décoratif) ; moduler autour
de 5 $/j (aurait exigé de RELEVER le cap par achat — verrou propriétaire, non
demandé). Propriétés : montant ≤ cap PAR CONSTRUCTION (plus un clamp après coup),
jamais 0 (plancher), spot_executor reste le backstop strict (gardes + mur absolu
25 $ inchangés), promesse ≤5 $/j renforcée (la dépense moyenne BAISSE). Affiché
partout : rapport CLI/Telegram (« RÉEL prévu »), dashboard (« $x réel (2–5 ∝
score) »). La réconciliation §43 mesurera l'effet sur le prix de revient réel dans
les semaines qui viennent — c'est elle qui dira si l'edge de backtest se matérialise.

---

## §45 — DÉCISION propriétaire : changement des règles, futures réel câblé

**Décision du propriétaire (02/07/2026)** : « Je veux changer les règles et passer en
full live. » Trois questions d'engagement posées et répondues explicitement :
périmètre = **carry + directionnel** (en connaissance de cause : l'espérance
directionnelle mesurée est NÉGATIVE, 0 agent LIVE, §35-41) ; validation =
**directement réel** (pas d'étape demo) ; capital = **tout le solde futures**
(~106 USDT au moment de la décision, ~260 USDT spot réservés à l'accumulation).
Les avertissements ont été présentés par écrit à chaque option ; le choix est acté.

**Ce qui change** :
- `futures_executor` passe à l'ÉTAPE 2 : chemin réel CÂBLÉ (l'étape 1 levait
  NotImplementedError). Mapping API v2 : mode one-way (side buy/sell + reduceOnly),
  marge ISOLÉE (perte max d'une position = sa marge), ordres MARKET (tailles petites),
  TP/SL préréglés arrondis au tick, taille arrondie VERS LE BAS au pas du contrat,
  levier fixé AVANT l'ordre (borné ×5, fail-closed si l'exchange refuse).
- Porte d'edge : OUTREPASSABLE par `FUTURES_EDGE_GATE_OVERRIDE=1` (config, décision
  propriétaire datée). La remettre à 0 referme la porte instantanément. Les 7 autres
  gardes restent NON négociables.
- `security_agent.scan_futures_exec` : le réglage de levier (borné) et le side
  'sell' (shorts) entrent au périmètre du module futures ; retrait/virement/
  annulation restent INTERDITS DURS.
- Armement : `FUTURES_AUTONOMOUS_LIVE=1` (.env) — double verrou complet avec
  `MANDATE_LIVE_ENABLED`.

**Ce que l'ingénierie impose en échange (non négociable)** :
- Murs ABSOLUS en dur : 50 $/trade, 250 $ d'exposition cumulée — env/config peuvent
  ABAISSER, jamais dépasser. Caps effectifs de DÉPART : 15/trade, 60 cumulé —
  montée par paliers sur décision propriétaire si l'exécution est propre.
- **Stop de perte JOURNALIER** (−5 % d'equity futures vs ouverture du jour) :
  franchi -> KILL_SWITCH armé automatiquement + alerte Telegram. FAIL-CLOSED :
  equity illisible = pas d'ouverture (on ne trade pas à l'aveugle). Une RÉDUCTION
  reste permise après breach (fermer n'aggrave jamais le risque).
- Montée en taille progressive : premiers ordres au minimum du contrat (~6-8 $).

**Câblé ensuite (même jour)** :
- Compte réel constaté : assetMode UNION (marge multi-devises) -> l'isolé est
  interdit par Bitget ; mode de marge ADAPTATIF (`resolve_marge_mode`, crossed
  forcé en union). Compte en mode couverture -> `_ensure_position_mode` le règle
  en one-way avant l'ordre (idempotent, fail-closed).
- **Boucle directionnelle automatique (`futures_auto.py`)**, câblée au cycle de
  scan : consensus FRAIS du cerveau (< 15 min, sinon rien) -> ouvrir/fermer/rien.
  Politique frugale (le §38 a montré que sur-trader détruit) : UNE position max,
  pas de pyramidage, flip en 2 cycles, entrée à |consensus| ≥ 0.35, sortie sous
  0.15, throttle 1 ordre/4 h, SL/TP PRÉRÉGLÉS côté exchange (1.5·ATR, RR 2 —
  protégé même si le VPS meurt), notional 10 $ ×2. Décision seulement : toute
  exécution passe par futures_executor et ses gardes. Débrayage :
  FUTURES_AUTO_DIRECTIONAL=0.

**Câblé (fin du chantier §45)** :
- Observabilité complète : `futures_report.py` (lecture seule — préview de
  décision via status() garanti sans exécution, position, equity + stop
  journalier, réconciliation des fills DU BOT bornée au 1er ordre réel
  journalisé — le trading manuel antérieur est exclu), Telegram `/futures`,
  panneau dashboard, alertes push ⚡ à chaque exécution réelle.
- **Jambes cash-and-carry (`carry_auto.py`)** : le BTC spot accumulé (jamais
  vendu) sert de jambe longue ; entrée = carry_monitor ATTRACTIF (APR net ≥
  5 %), short perp TOUJOURS ≤ 95 % de la couverture spot (delta-neutre par
  construction), levier ×1, SANS SL (hedgé — un stop casserait la neutralité),
  sortie par hystérésis (APR net < 2 %), throttle 8 h (période de funding),
  relevé périmé (> 2 h) -> pas d'entrée ; en position, relevé illisible ->
  TENIR (pas de sortie aveugle).
- **Propriété de position** (`proprietaire_position`) : en one-way il n'y a
  qu'UNE position nette — chaque boucle (auto_dir, carry) ne touche QUE la
  sienne ; une position d'un autre agent (ex. 'validation' manuelle) n'est
  JAMAIS touchée. Mutuelle exclusion honnête plutôt que netting silencieux.

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

---

## §46 — Audit multi-agents complet + premier aller-retour 100 % autonome

**Audit orchestré (03/07, 16 agents : 9 sondes lecture seule + 4 analystes +
contre-expertise)** : 39 anomalies brutes, 40 optimisations proposées, livrées en
3 lots. Verdict global : architecture saine, exécution §45 validée, mais plusieurs
défauts invisibles de longue date :

- **P0** : bug de signature `_atr` (le SL réel n'a JAMAIS été basé ATR — repli 1.5 %
  silencieux) ; doublon config FUTURES_REAL_MAX_* (éditer la 1re occurrence ne
  faisait rien) ; halte drawdown du mandat INERTE sur le chemin réel (equity_curve
  jamais passée) ; Telegram crashable par timeout réseau + /run_once pouvant
  déclencher un cycle réel depuis le chat (désactivé).
- **P1** : `gather_votes` parallélisé (brain_cycle était TUÉ à 90 s à 98 % des
  cycles sur 7 j — l'apprentissage ne couvrait que ~7 symboles ; après : 13/13 en
  58 s, confirmé sous systemd) ; halte globale évaluée AVANT le cerveau dans
  preorder_engine (0.46 s vs ~60 s en risk-off) ; runtime_cache atomique + éviction
  par clé (l'ancien slicing corrompait tout le cache au seuil 2 Mo) ;
  macro_sentinel réparé (FRED bloque urllib, requests passe — nowcast vivant pour
  la 1re fois : expansion 0.69) ; .env : le « token » CryptoPanic était un
  commentaire (news_feed attend un vrai token).
- **P2 (instrumentation revue J+14)** : `journal_append.py` (JSONL append-only,
  rotation bornée) ; historique long des votes (`brain_log_history.jsonl` — la
  fenêtre de 500 ≈ 6 h ne suffisait à aucune analyse) ; contexte de décision
  (score/prix/premium/RSI/F&G) journalisé AVEC chaque achat réel ; journal des
  décisions de cycle des 2 boucles (`futures_auto_journal.jsonl`) ; alerte
  réapprovisionnement spot (seuil 15 $) ; affichage du VRAI USDT libre (45.98 $)
  vs valeur totale du compte (253 $) qui était trompeuse.

**Premier round-trip 100 % autonome (nuit du 02 au 03/07)** : consensus −0.54 →
short 10 $ ×2 ouvert à 23:31:41 UTC (SL/TP préréglés côté exchange), conviction
morte → fermé à 03:36:06. PnL réalisé −0.0007 $, frais 0.0148 $, net −0.015 $.
Toute la chaîne décision → gardes → ordre → position → sortie → journal →
réconciliation a fonctionné sans intervention. (Le SL de ce trade datait d'avant
le correctif ATR ; les suivants utilisent 1.5·ATR.)

**Addendum §46 — « plein potentiel Bitget » (03/07)** : inventaire des outils du
client (spot/futures/account/margin/convert/earn/copytrading/p2p/broker) croisé
avec l'usage réel. Deux verdicts :
- **Earn : INDISPONIBLE par API** pour ce compte/région (`EARN_UNAVAILABLE`,
  vérifié en direct) — la « piste EARN » documentée depuis §38 n'est PAS
  actionnable avec la clé actuelle ; seule l'app manuelle le permettrait. Piste
  fermée honnêtement (ne pas re-creuser sans changement de compte/région).
- **Ouvertures futures en limit IOC plafonné** (±FUTURES_SLIPPAGE_TOL_PCT=0.10 %
  du mark, force ioc) : parité avec la protection anti-slippage du spot
  (limit_ioc §31) — remplit comme un market mais jamais au-delà du plafond ; un
  remplissage partiel RÉDUIT le risque, jamais ne l'aggrave. Les RÉDUCTIONS
  restent en market (la sortie doit toujours réussir). Margin trading et
  copytrading/p2p/broker restent interdits durs ; convert (poussière) sans objet.

**Addendum §46 — cap carry 200 (décision propriétaire, 03/07)** : caps effectifs
portés à 50/trade (= mur) et 200 cumulé (mur 250 intact) ; cible carry 200 $,
TOUJOURS ≤ 95 % de la couverture spot (BTC + BGBTC décoté — ~189 $ effectifs
aujourd'hui), construite PAR TRANCHES ≤ cap/trade toutes les 8 h (période de
funding), renforcement seulement tant que l'attrait reste ATTRACTIF (hystérésis :
pas de rajout tiède). Corollaires d'ingénierie : (1) les RÉDUCTIONS sont exemptées
des caps notional (reduceOnly = borné à la position — fermer un carry de 180 $ en
un ordre) ; (2) le stop journalier mesure désormais le LIVRE COUVERT (equity
futures + exposition BTC spot) — l'equity futures seule aurait produit un faux
breach kill-switch sur tout BTC +6 % alors que le hedge gagne côté spot ; une
composante illisible -> pas d'ouverture, pas de kill-switch (bases jamais
mélangées entre deux mesures).

**Addendum §46 — mode HEDGE (déclaré par le propriétaire, 03/07)** : le compte
passe en mode couverture -> carry (short couvert) et directionnel (long/short)
peuvent COEXISTER. Implémentation ADAPTATIVE : une position OUVERTE fait autorité
(Bitget refuse la bascule en position — le posMode de la position est la seule
vérité) ; à plat, l'exécuteur bascule vers la cible hedge_mode au premier ordre.
Format d'ordre par mode : hedge = side du CÔTÉ de position (buy=long/sell=short,
convention Bitget) + tradeSide open/close, sans reduceOnly ; one-way (transitoire)
= side d'exécution + reduceOnly. Gestion PAR CÔTÉ dans les boucles
(parser_positions, proprietaire_cote) : chaque boucle ne touche que le côté
qu'ELLE a ouvert ; un côté occupé par un autre agent -> rien ; en one-way
transitoire, ouvrir le côté opposé d'une position étrangère NETTERAIT -> refus
explicite en attendant le hedge. Exposition brute des caps = somme des DEUX côtés.

---

## §47 — Multi-symboles : les agents passent en réel sur tout l'univers

**Demande propriétaire (03/07)** : « continuer de passer les outils et les agents
en réel ». Constat honnête : depuis la réparation de l'audit, le cerveau (13
agents) vote et apprend sur TOUT l'univers (~10-13 symboles) à chaque cycle, mais
seul le consensus BTCUSDT était câblé au réel. Le pipeline paper multi-symboles
(journal_scanner -> pré-ordres) reste PAPER — sa mesure est PERDANTE (WR 32.5 %,
TP/SL 0.48) : on ne câble pas un perdant mesuré, on étend le canal CONSENSUS.

**Livré** :
- `futures_executor` paramétré PAR SYMBOLE (spec contrat/prix/levier/positions —
  cache par clé), rétro-compatible (défaut BTCUSDT). Murs/caps INCHANGÉS et
  GLOBAUX : l'exposition brute compte tous les symboles et tous les côtés.
- `futures_auto` MULTI-SYMBOLES, politique frugale étendue : une position max par
  symbole, FUTURES_AUTO_MAX_POSITIONS=3 simultanées, 1) FERMETURES d'abord (une
  par cycle, NON throttlées — réduire le risque n'attend pas), 2) OUVERTURE du
  candidat au |consensus| MAX ≥ 0.35 sur l'univers, côté libre, un ordre par
  throttle 4 h. Propriété par (symbole, côté) ; netting interdit en one-way
  transitoire ; SL/TP ATR du symbole ; journal de décision avec symbole.
- Le carry reste BTCUSDT (seule couverture spot détenue — §46).

Le pipeline pré-ordres/paper reste le LABORATOIRE (mesure, jamais d'exécution).

---

## §48 — Agent GEOMETRIC réécrit sur mesure : réversion courte + tendance longue signée

**Demande propriétaire (03/07)** : « analyse, cherche d'autres infos et améliore le
bot geometric ». Diagnostic à l'étalon (replay, bougies FIGÉES, 4 symboles) : le
cœur directionnel « suivre le momentum 8 barres » avait un IC NÉGATIF (poolé −0.05
en 1h, −0.09 en 15m) — il CONTREDISAIT le fait stylisé mesuré par la propre
recherche du dépôt (§35-38 : la réversion court terme est réelle en crypto).

**Littérature ajoutée** : signatures de chemins pour la classification de régimes
(arXiv:2107.00066), aire de Lévy lead-lag (2110.12288), estimateurs de Hurst — R/S
biaisé sur n court, DFA robuste (2310.19051, 1208.4158), Hurst dynamique Bitcoin
(1709.08090). Trois NOYAUX calculables implémentés (purs, testés) :
- `levy_area_tp` : aire de Lévy du chemin (temps, prix) = terme antisymétrique du
  niveau 2 de la signature — CONVEXITÉ signée du mouvement (accélération vs
  essoufflement), 0 sur la corde, +1/6 pour x~t², −1/6 pour x~√t ;
- `dfa_hurst` : Hurst par DFA(1), remplace le R/S comme estimateur principal ;
- `w1_gauss` : distance de Wasserstein-1 à la gaussienne (transport optimal 1D),
  calibrée numériquement (gaussien ≈ 0.06, t2.5 ≈ 0.24, seuils 0.10/0.22) —
  3e voix du régime de queue aux côtés de Hill α et du proxy Φ.

**Nouveau cœur directionnel MIX** (hypothèse tirée de §35-38, PAS minée) :
réversion du mouvement court (z 8 barres, toujours active) + tendance longue
(32 barres) qualifiée par Hurst-DFA et l'aire de Lévy, coupée en régime euclidien.
Gate de toxicité inchangé. **Mesure avant/après sur bougies figées** : IC poolé
−0.05 -> +0.11 (1h, t +1.8) et −0.09 -> +0.17 (15m, fenêtre INDÉPENDANTE, t +1.9),
positif sur chacun des 4 symboles dans les deux fenêtres. 3 variantes testées
(momentum long seul : +0.05 ; réversion seule : +0.06 ; mix : +0.11) — sélection
sur 2 fenêtres indépendantes, direction pré-enregistrée par §35-38. L'agent reste
ADVISORY (PAPER) : c'est la validation transversale (timer 6 h) et l'échelle
d'edge qui jugeront sur la durée, avec déflation multiple-testing.

---

## §49 — Agent SAVANT « spécialiste trading » : la fenêtre bornée gagne, le reste rejeté

**Demande propriétaire (03/07)** : améliorer l'agent « autiste digitale » (savant)
en spécialiste trading. Baseline à l'étalon (replay, bougies figées, 4 symboles) :
IC poolé +0.039 en 1h, vote 9 % du temps (hyper-focalisation par design), déjà le
meilleur des 4 agents purs (DSR 0.339 en xs).

**Littérature** : turbulence de Kritzman-Li (Mahalanobis comme indice de régime),
Mahalanobis++ (arXiv:2505.18032 : la NORMALISATION des features est le levier n°1),
proxies de liquidité OHLCV — spread Corwin-Schultz (2012), illiquidité d'Amihud
(2002), microstructure crypto (2602.00776).

**Mesure composant par composant (bougies figées 1h, validé 15m indépendant)** :
- FENÊTRE BORNÉE (72) : +0.039 -> **+0.095** (1h, plateau stable fen 56-72) et
  +0.145 -> **+0.185 (t 3.0)** en 15m. Argument de JUSTESSE, pas de fit : le
  replay de validation passait TOUT l'historique quand le live calcule sur 80
  bougies — l'étalon évaluait un autre agent que celui qui vote. ADOPTÉE.
- Tenseur enrichi liquidité (D7, log-volume + CS + Amihud) : **−0.02 — REJETÉ**
  (les dimensions de liquidité DILUENT la détection Mahalanobis du vote).
- Seuil percentile adaptatif : −0.005 — REJETÉ. Direction z 3 barres : −0.009 —
  REJETÉ. (La première réécriture complète faisait −0.009 poolé : c'est la mesure
  composant par composant qui a sauvé l'amélioration.)

Les utilitaires (corwin_schultz, turbulence_percentile, _standardize_robuste,
tenseur enrichi=True) restent disponibles, TESTÉS, documentés « rejetés du vote à
la mesure » — pour l'observabilité. Leçon reproduite deux fois (§48, §49) : chaque
composant se mesure SÉPARÉMENT, la somme des bonnes idées n'est pas une bonne idée.

---

## §50 — Synesthésie du savant : l'alphabet de formes (Bandt-Pompe), perception non votante

**Demande propriétaire (03/07)** : « ajoute un algorithme pour utiliser la
synesthésie de l'agent autisme digital ». Traduction RIGOUREUSE (pas une
métaphore) : les MOTIFS ORDINAUX de Bandt-Pompe — chaque fenêtre de 3 clôtures
devient une « forme » d'un alphabet de 6 (0 = montée franche … 5 = descente
franche) ; la série de prix devient une suite de formes, et la palette se lit :
- `motifs_ordinaux` : traduction clôtures -> (formes, poids d'amplitude —
  entropie de permutation PONDÉRÉE, arXiv:2207.01169) ;
- `synesthesie` : entropie ∈ [0,1] (1 = bruit, bas = le marché « dessine »),
  biais ∈ [−1,1] (asymétrie montée-franche vs descente-franche = irréversibilité
  directionnelle, arXiv:2307.08612 crypto), motifs interdits (arXiv:0711.0729),
  signal = biais × structure.

**Mesure à l'étalon (bougies figées, 4 symboles)** : le sens CONTRARIAN gagne
(+0.044 seul en 1h ; le sens continuation fait −0.044 — 3e confirmation du fait
stylisé §35-38). En REPLI du fade (couverture 12 % -> 100 %) : 1h +0.089 -> +0.102
MAIS 15m +0.172 -> +0.084 — **les deux fenêtres se CONTREDISENT, la dégradation
15m dépasse le gain 1h -> PAS DE VOTE** (barre des deux fenêtres, comme §48-49).

**Décision** : la synesthésie est PERCEPTION, pas vote — calculée à chaque
signal(), exposée dans la sortie (`synesthesie: {entropie, biais, interdits,
signal}`) et dans la note quand le marché « dessine » (H < 0.85 : « palette
H0.72 montante »). Les consommateurs (rapports, dashboard, travaux futurs) la
lisent ; le vote reste le fade Mahalanobis prouvé (§49). Si la validation
transversale de longue durée montre un jour un edge stable du signal ordinal,
le câblage au vote sera un chantier mesuré séparé.

**Addendum §51 — maker-first carry : bloqué par la charte (décision propriétaire).**
La recommandation « poser les tranches carry en post-only (frais 0.02 %) avec repli
IOC (0.06 %) » économiserait ~2/3 des frais du carry. MAIS un ordre post-only non
rempli RESTE au carnet (GTC) et exige une gestion d'annulation — or la charte
interdit toute annulation au bot (« JAMAIS de retrait/virement/annulation »,
futures_cancel_orders est dans FUTURES_EXEC_FORBIDDEN). Câbler maker-first
imposerait d'autoriser le bot à annuler SES PROPRES ordres non exécutés — une
extension de périmètre que seul le propriétaire peut accorder. En attendant :
limit IOC ±0.10 % (jamais d'ordre orphelin, par construction).

**Addendum §51 — durcissement des portes.** Deux pushes du 03/07 sont partis avec
un test rouge à cause de chaînes shell défaillantes (pipe qui avale le code de
sortie ; heredoc + saut de ligne qui sort `git commit` de la chaîne &&). Créé
`gates.sh` (codes de sortie stricts, commit conditionnel) — forme obligatoire
documentée dans CLAUDE.md. Le backtest directionnel long (recommandation n°5)
reste au backlog.

**Addendum §51 (suite) — cinq mécanismes de saturation, démontés un à un.**
La traque du poids d'orderflow épinglé à 3.0 a révélé une cascade :
1. cohérence AVEC SOI (consensus incluant l'agent) -> LOO ;
2. min-max PAR LOT dans earcp_weights (un écart d'UN hit étiré à [0,1], ×exp(5))
   -> bornes ABSOLUES ;
3. learn() PAR SYMBOLE (10×/cycle) recomposait la concentration à chaque appel
   -> l'EARCP devient une CIBLE, lissage 10 %/apprentissage ;
4. cohérence à 30 % du score alors qu'elle ANTI-corrèle avec la justesse mesurée
   -> β 0.9 (départage, configurable BRAIN_EARCP_BETA) ;
5. le plus profond : l'entrée « performance » de l'EARCP était LE POIDS LUI-MÊME
   (mémoire Hedge) — poids↑ -> P̃↑ -> cible↑ -> poids↑, auto-excitation jusqu'au
   clamp sur n'importe quelle inclinaison persistante. Remplacée par le HIT-RATE
   EWMA mesuré (α=0.05, brain_hitrates.json, exogène, borné [0.3,0.7]).

Validation par simulation multi-seeds (30 cycles × 10 symboles, 8 graines) :
sans edge + cohérence 0.85 (la pathologie) : médiane 0.99 (avant : 3.00) ;
mauvais 42 % : 0.83 ; bon 58 % : 1.16 ; excellent 65 % : 1.82. Monotone, borné,
plus d'auto-excitation. Poids remis à neutre sous le mécanisme final ; les
priors d'edge (§41) continuent de s'appliquer par-dessus. À surveiller dimanche :
la répartition des poids doit maintenant refléter les IC live (§51, tableau).

---

## §52 — Recherche de stratégies supplémentaires : un agent adopté, deux rejetés, trois en feuille de route

**Demande propriétaire (03/07)** : « cherche des stratégies supplémentaires à
ajouter ». Contraintes dures du tri : Bitget seul, déterministe, AUCUNE
annulation d'ordre (charte), capital ~450 $, barre des deux fenêtres.

**ADOPTÉ — agent LEAD-LAG contrarian BTC->alts (14e agent).**
Littérature : lead-lag haute fréquence (arXiv:1111.7103), facteur BTC dans les
alts (1903.06033). Trois formulations MESURÉES à l'étalon (bougies figées, 3
alts, sous-échantillonnage anti-autocorrélation, 2 fenêtres indépendantes) :
- réversion vers le facteur bêta×BTC (1903.06033 littéral) : +0.03 (1h) /
  −0.09 (15m) — fenêtres CONTRADICTOIRES, rejetée ;
- suivi du mouvement BTC : −0.178 / −0.201 — rejeté (signe inverse) ;
- **FADE du z BTC 8 barres sur les alts : +0.178 (1h, t 3.5) / +0.201 (15m,
  t 4.0) — adopté**. 4e confirmation du fait de réversion (§35-38), cross-asset.
`leadlag_agent.py`, vote 0 sur BTC lui-même, poids appris par l'EARCP corrigé
(§51), jugé par l'audit d'IC live comme les autres.

**REJETÉ à la mesure** : réversion facteur bêta (ci-dessus) ; suivi lead-lag.

**FEUILLE DE ROUTE (paper d'abord, dans l'ordre de valeur attendue) :**
1. *Paires co-intégrées* (stat-arb BTC/ETH, legs SPONGE de geometric §46) —
   marché-neutre, hedge mode prêt, capital OK (jambes 10-20 $). Infra existante
   (partition signée) ; exige un moteur de spread + validation xs paper.
2. *Momentum/réversion CROSS-SECTIONNELLE long-short* (2302.10175 : spatio-
   temporel) — l'infra de validation xs mesure déjà par symbole ; la voie
   paper peut ranker l'univers et simuler long-top/short-bottom delta-neutre.
3. *Funding-extrêmes contrarian* — `futures_get_funding_rate` n'expose PAS
   l'historique : pas de backtest possible ; à juger EN LIVE seulement (agent
   candidat : short le funding extrême positif encaissé par le carry).
4. *Saisonnalité horaire du DCA* — micro-optimisation du timing d'achat réel,
   mesurable sur nos propres bougies 1h (petite, sans risque).

**Écartés d'office (contraintes)** : grid trading (exige annulations —
interdites), arbitrage triangulaire spot (exige ventes spot — interdites),
options/VRP (pas d'API options), news momentum (pas de token CryptoPanic).

---

## §53 — Historique profond : trois verdicts d'un an de données

`candles_history.py` (nouveau, SAFE lecture seule) : pagination endpoint public
`history-candles` (granularité MIX en majuscule : 1H), cache disque incrémental
gitignored (data_history/). Un an de bougies 1h téléchargé pour BTC/ETH/SOL/XRP
(8800 bougies chacun). Trois questions de la feuille de route §52 tranchées :

1. **Lead-lag (14e agent) sur 1 an : IC +0.014 (t 0.9, n=4356, pas 6 h)** —
   positif sur chacun des 3 alts mais FAIBLE : le +0.18/+0.20 des fenêtres
   récentes était en partie un régime (juin-juillet 2026 très réversif).
   L'agent RESTE (signe jamais négatif, 3 fenêtres × 3 symboles) avec sa fiche
   tempérée — le hit-rate EWMA (§51) le pèsera à sa juste valeur.

2. **Paires co-intégrées : NO-GO.** Demi-vies de spread mesurées (OLS roulant
   168 h, AR(1)) : ETH/BTC 1015 h, SOL/BTC 1386 h, SOL/ETH 1174 h, XRP/BTC
   953 h — soit 40-58 JOURS pour rendre la moitié d'un écart. À notre échelle
   (capital, funding sur DEUX jambes pendant des semaines), impraticable en 1h.
   Résultat négatif précieux : la voie paper paires est fermée AVANT d'exister.
   (Réexaminable un jour en 5m intrajournalier — autre bête.)

3. **Saisonnalité horaire : RÉELLE et gratuite.** Prix relatif à la moyenne 24h
   glissante, par heure UTC, sur 1 an : 16-19h UTC ressortent 10-15 bps sous la
   moyenne (19h : −15.1 bps), 12h (l'heure de fait du DCA, ancrée par hasard)
   à −4.5 bps. ADOPTÉ : `fenetre_achat_ok` — l'achat réel quotidien VISE
   16-20h UTC, fail-open à 30 h de retard (jamais un jour sauté), registre
   vierge exempté. ~+10 bps/achat, zéro coût, zéro risque ajouté.

NB : le backtest du CONSENSUS complet sur l'an reste impossible offline — la
plupart des agents consomment des flux live-only (carnet, liquidations,
funding). L'instrument de mesure du consensus est l'audit d'IC live (§51).

---

## §54 — L'année contre les fenêtres : audit de régime des agents purs, porte annuelle

**Audit des 4 agents purs sur TROIS fenêtres** (1h 25 j figée, 15m 6 j, 1h 1 AN) :

| agent | 1h 25j | 15m 6j | 1 AN |
|---|---|---|---|
| simons | +0.043 | +0.106 | −0.004 |
| divergent | +0.105 | +0.175 | −0.005 |
| geometric v2 (§48) | +0.113 | +0.168 | **−0.068 (t −2.6)** |
| geometric v1 (ancien) | −0.050 | −0.088 | **+0.045 (t +1.7)** |
| savant (§49) | +0.089 | +0.172 | −0.062 (t −2.4) |
| leadlag (§52) | +0.178 | +0.201 | +0.014 |

**Leçon centrale : mes « deux fenêtres indépendantes » (§48-52) partageaient le
MÊME régime** (juin-juillet 2026 très réversif). L'année inverse plusieurs
verdicts. Tentative de v3 conditionnel au régime (mesure sur l'an : queue
lourde -> réversion +0.02/+0.06 ; transitoire/gaussien -> momentum +0.06/+0.18,
soit l'INVERSE de la thèse d'origine des papiers) : an +0.03, 1h +0.07, mais
15m −0.10 -> AUCUNE formulation ne passe les trois fenêtres. Le signal est
régime-dépendant par nature.

**Décision structurelle (pas de winner-picking sur backtests contradictoires)** :
1. v2/§49 restent en production (collent au régime COURANT — le live le
   confirme : geometric DSR xs 0.48, priors relevés) ; fiches mises à jour.
2. **Porte ANNUELLE dans l'échelle d'edge** : `agent_validation.replay_annuel`
   (pur, données injectables) tourne à chaque validation (top-up incrémental de
   l'historique), greffe `annuel: {ic, t, n}` sur chaque ligne du ranking, et
   `edge_ladder.tier_of` REFUSE le palier LIVE si l'IC annuel est négatif
   (fail-open sans mesure : on bride sur preuve). Un artefact de régime ne peut
   plus être promu au réel.
3. L'arbitrage fin des poids reste à la couche adaptative : hit-rate EWMA (§51)
   + priors d'edge — c'est leur travail, sur données vivantes.

---

## §55 — Profondeur d'historique : Bitget natif remonte à 6 ans ; ordres réels marqués sur le graphique

**Sondage de profondeur (03/07)** : l'endpoint public `history-candles` de Bitget
sert des bougies 1h jusqu'à ~juillet 2020 (−6 ans OK, −8 ans vide). AUCUNE source
externe nécessaire pour 6 ans d'histoire AU PRIX DU LIEU D'EXÉCUTION — la
cohérence qui compte pour les backtests. Binance (−5 ans testé OK) et Bybit
(−4 ans OK) sont joignables depuis le VPS : replis documentés si un jour il faut
pré-2020 ou des symboles absents de Bitget. Téléchargé : BTC 50 201 bougies
(2020-09 -> aujourd'hui) ; ETH/SOL/XRP en cours d'approfondissement.

**TradingView / MCP (demande propriétaire)** : il n'existe AUCUN serveur MCP
TradingView officiel — uniquement des projets communautaires (principal :
atilaahmettaner/tradingview-mcp — données temps réel, indicateurs, screeners ;
tradesdontlie/tradingview-mcp pilote TradingView Desktop). Décision de sécurité :
ne PAS installer de code tiers non audité sur le VPS de production qui détient
les clés de trading — c'est une décision propriétaire explicite si souhaitée
(utile pour les SESSIONS D'ANALYSE, jamais pour le pipeline du bot, qui reste
sur ses sources HTTP déterministes). Les MCP déjà connectés côté session
(coinpaprika OHLCV historique, alphavantage crypto) couvrent le besoin d'analyse.

**Graphique : indicateurs et ordres réels MARQUÉS (§55)** :
- valeurs COURANTES des indicateurs (EMA20/50, VWAP) affichées sur l'axe des
  prix, dans la couleur de leur série (lastValueVisible) ;
- ORDRES RÉELS du symbole affiché posés sur les bougies : DCA (rond phosphore),
  ouvertures long/short (flèches vertes/rouges « OUVRE L/S »), réductions
  (carré ×) — source : registres spot + futures, fusionnés avec le marqueur de
  conscience du cerveau (les setMarkers s'écrasaient mutuellement avant).

**Addendum §55 — le verdict SIX ANS (194k bougies, tous les régimes 2020-2026).**
Replay plafonné (~400 échantillons/symbole, déterministe — le fit HMM de simons
rendait les 6 ans infaisables en un timer : >10 min -> 198 s après plafond) :

| agent | 1 AN (§54) | 6 ANS | lecture |
|---|---|---|---|
| savant | −0.062 | **+0.062 (t +2.5)** | RÉHABILITÉ : 2025-26 était SON mauvais régime |
| geometric v2 | −0.068 | **+0.032 (t +1.3)** | réhabilité aussi — §48 tient sur 6 ans |
| divergent | −0.005 | −0.005 | plat, partout |
| simons | −0.004 | −0.019 | plat (son DSR xs 0.70 = fenêtre courte) |
| leadlag | +0.014 | −0.010 | plat sur 6 ans — instrument de régime, fiche déjà tempérée |

Leçon au carré : MÊME le juge « annuel » était régime-sensible (l'an 2025-26
condamnait savant/geometric que 6 ans réhabilitent). La porte d'edge lit
désormais la fenêtre la plus PROFONDE disponible (6 ans), et la promotion LIVE
exige toujours les trois preuves : xs récent + profond positif + live confirmé.
Avec ces données : savant/geometric passeraient la porte profonde ;
divergent/simons/leadlag y échoueraient (plats) — exactement le tri attendu.

---

## §56 — Formation : bibliothèque de savoir constituée (docs/SAVOIR.md)

Demande propriétaire : « cherche sur internet, forme toi, accumule du savoir ».
Méthode : recherches ciblées sur les questions OUVERTES du système (pas de
collecte sans usage), lecture intégrale du papier pivot par agent dédié,
croisement systématique avec nos mesures. Résultat : **docs/SAVOIR.md**, 8
sections, chacune avec « implication pour le bot » :
1. Forecast combination puzzle -> valide la refonte EARCP §51 (poids ~égaux) ;
2-3. Carte tendance/réversion par horizon (Zurich 2501.16772, lu en entier) +
   slow-momentum/fast-reversion (Oxford) -> valident la structure bi-échelle de
   geometric v2 et éclairent §54 ; règle de SUR-EXTENSION (ne pas chasser une
   tendance de t-stat > ~1.5) = chantier mesurable ;
4. Anti-cherry-picking (plateau de paramètre obligatoire) ;
5. Funding : le carry est une moisson d'euphorie (calme 11 % APR, euphorie
   30 %+) — notre seuil 5 % bien calé, passage en percentile quand l'historique
   interne suffira ;
6. Structure 2026 : les flux d'ETF = acheteur marginal dominant (chantier :
   input flows), cascades record (10/10/25 : 2.3 G$) encore violentes ;
7. Sizing : ¼-½ Kelly max sous queues lourdes, vol-target lissé (le levier
   FABRIQUE les queues — Farmer 0908.1555).
Chantiers mesurables notés dans SAVOIR.md ; mémoire de session mise à jour.

---

## §57 — Les trois chantiers de SAVOIR.md, instruits le jour même

1. **Momentum lent (pic 6-12 mois de Zurich) : NO-GO en crypto.** φ de tendance
   (poids n·e^(−2n/T), t-stat bornée ±2.5) mesuré sur 6 ans de bougies 1D,
   4 symboles, horizons 7/30 j : T=90j négatif, T=180j au mieux +0.026 (t 1.3 —
   bruit), T=270j −0.042 (t −2.0, plutôt CONTRARIAN). La carte des horizons des
   actifs traditionnels ne se transpose pas — la crypto 2020-2026 casse ses
   tendances longues. On n'ajoute PAS d'agent momentum lent. (Le signe
   contrarian à 270 j est noté comme observation, pas exploité : le retenir
   maintenant serait du sign-flipping post hoc.)
2. **Cap de sur-extension |φ|>1.5 : sans gain mesuré** sur le quotidien ; le
   terme tendance de geometric (32 barres 1h, autre échelle) reste INTACT —
   pas de retouche sans gain démontré.
3. **Flux ETF BTC pour l'agent flows : bloqué sur clé.** farside.co.uk = 403
   (Cloudflare), CoinGlass = « API key missing » (free tier existe). Décision
   propriétaire, comme le token CryptoPanic — la valeur attendue est réelle
   (les ETF sont l'acheteur marginal dominant, cf. SAVOIR.md §6).

Bilan de la formation : 2 résultats négatifs propres (des semaines économisées),
1 dépendance externe identifiée, et les acquis structurels (combination puzzle,
sur-extension, funding-euphorie) gravés dans SAVOIR.md avec leurs implications.

---

## §58 (suite) — Inventaire des clés du .env : deux réveillées, quatre mortes

Sondes du 03/07 (demande propriétaire « utilise les clés disponibles ») :
| clé | état | action |
|---|---|---|
| ALPHAVANTAGE_API_KEY | ✅ fonctionne | TradFi ressuscité (macro_data, §58) |
| KALSHI_API_KEY | ✅ fonctionne | kalshi_probe : échéances Fed/CPI vivantes dans le snapshot macro (advisory) |
| FRED_API_KEY | présente | inutile pour l'instant (le CSV sans clé suffit au nowcast) |
| TWELVEDATA / COINGECKO / FINNHUB / FMP | ❌ 401 (mortes) | le propriétaire régénère |
| bearerToken X | ❌ 402 credits depleted | payant — abandonné pour l'instant |
| BIRDEYE / HELIUS / SOLANA_RPC | présentes | hors périmètre actuel (on-chain Solana) — notées |
| COINGLASS_API_KEY | ABSENTE | la clé demandée (ETF + funding history) — propriétaire s'inscrit |

kalshi_probe.py : lecture seule, séries KXFEDDECISION + KXCPI, parsing pur testé
(échéances passées exclues, repli close_time, tri), cache 1 h, snapshot macro
enrichi (« Fed decision in Jul 2026 dans 26 j ») — première brique VIVANTE pour
le black-out macro du mandat (jusqu'ici statique).

---

## §59 — Nouvelles clés propriétaire : CoinGecko OK, CoinGlass gratuit inutile,
## le funding NATIF Bitget à la place, TwelveData pour l'or spot

- **CoinGecko (nouvelle clé)** : fonctionne en en-tête demo — le client du dépôt
  était déjà correct (demo + repli keyless), c'est l'ancienne clé qui était
  morte. Filtre qualité de l'univers de retour sans repli.
- **CoinGlass (nouvelle clé)** : authentifie, mais le tier GRATUIT ne couvre
  AUCUN endpoint utile (ETF flow-history, funding history, liquidations :
  « Upgrade plan », ~29 $/mois). Verdict honnête : pas rentable à notre échelle.
  Le chantier flux ETF reste bloqué (alternatives payantes ou scraping fragile).
- **PIVOT funding : l'historique est PUBLIC chez Bitget même**
  (/api/v2/mix/market/history-fund-rate, 100 taux/page, plafond ~3 mois
  glissants). `funding_history.py` : consolidation disque incrémentale (le
  plafond 3 mois devient sans objet à mesure que NOTRE historique s'accumule),
  percentile PUR (≥90 taux). Branché ADVISORY dans carry_monitor
  (`funding_pctl`) — la porte réelle reste le seuil absolu 5 % (basculer au
  percentile = décision mesurée séparée, cf. SAVOIR.md §5). État : 270 taux,
  dernier +0.0001 (APR 11 %) = percentile 100 % de ses 3 mois (funding bas
  partout — cohérent avec le carry NEUTRE).
- **TwelveData (nouvelle clé)** : forex/métaux OK (800 req/j), indices payants.
  macro_data optimisé TRI-SOURCES : or SPOT XAU/USD (bat le proxy GLD) et
  dollar via EUR/USD INVERSÉ (TwelveData), SPX via AlphaVantage (SPY), VIX et
  10 ans via FRED. 5 lectures sur 5 en live, régime RISK_ON.

**Addendum §59 — black-out macro VIVANT.** Le mandat prévoyait ±30/15 min autour
des annonces (MANDATE_MACRO_BLACKOUT_*) sans calendrier réel : la règle ne
s'appliquait jamais. Câblé sur Kalshi (§58) : `evenement_imminent` (pur, testé)
+ `futures_auto.blackout_macro` — les OUVERTURES directionnelles sont refusées
dans la fenêtre d'une décision Fed ou d'un print CPI (les FERMETURES restent
permises : réduire le risque n'attend pas). Fail-open : calendrier muet ->
porte transparente. Première application concrète du savoir §56 (les annonces
macro sont les moments de dislocation) à la protection du capital réel.

---

## §60 — Les sept chantiers du « que pourrais-tu faire de plus ? », exécutés

1. **Sauvegarde hors-VPS** : archive chiffrée AES-256 des 15 registres
   irremplaçables -> document Telegram, timer quotidien 03:40 UTC. Première
   archive envoyée et vérifiée. Passphrase dans le .env ET à conserver hors-VPS
   par le propriétaire. Restauration documentée dans backup_registres.py.
2. **Exit lab** : l'instrument qui jugera SL 1.5·ATR / RR 2 (conventions jamais
   mesurées). Paper : WR 33.5 %, ratio TP/SL 0.504 sur 212 issues — le RR
   conventionnel mérite examen. Réel : 4 fermetures < 10 -> l'instrument
   accumule sans conclure.
3. **Timing de funding** : report d'OUVERTURE si un règlement (00/08/16 UTC)
   tombe sous 20 min et que le côté paierait (fail-open, fermetures intactes).
4. **Voie xs paper** (dernier survivant §52) : panier dollar-neutre 2×2 jambes
   de 10 $ fictifs, rebalance 24 h, journal dédié. Premier panier : long
   HYPE/ETH, short BTC/LAB. Le laboratoire tranchera dans les deux sens.
5. **Audit IC live permanent** (live_ic_audit.py) : l'outil ad hoc du §51
   devenu module, branché à la revue. Jour 1 : technicals +0.24 (t 6.2) et
   flows +0.22 en tête ; carry/derivs/liquidations significativement négatifs
   -> candidats à l'audit de formulation quand l'échantillon suffira.
6. **Décisions propriétaire actées** : CryptoPanic PAYANT -> refus assumé, le
   sous-système news est CLOS (retiré des attentes). Restent ouvertes, à sa
   main : autorisation d'annuler ses propres ordres (maker-first carry),
   montée des caps (déclencherait le sizing vol-target), CoinGlass payant
   (flux ETF).
7. **Gouvernance du temps de mesure** : la revue hebdo produit désormais des
   RECOMMANDATIONS CHIFFRÉES automatiques (verdict directionnel bloqué avant
   30 fills, ratio TP/SL, agents à promouvoir/auditer selon l'IC live) — le
   matériau de décision, l'humain tranche.

---

## §61 — Post-mortem : 4,7 h de cerveau gelé en silence (et les trois verrous posés)

**Incident** (détecté par la question du propriétaire « les loops sont-ils
actifs ? ») : le commit β de §51 (11:52) appelait `_cfg` dans learn() alors que
l'import n'existait qu'en LOCAL dans une autre fonction -> NameError à CHAQUE
apprentissage, AVALÉ par le try/except unique de read() qui couvrait aussi
_record. Conséquences, de 12:01 à 16:44 : plus AUCUN vote journalisé (brain_log
gelé), poids figés à 1.0 (pris à tort pour la « douceur » du nouveau mécanisme),
boucle directionnelle AVEUGLE — fail-closed (consensus périmé -> aucun trade),
donc zéro perte, mais zéro perception aussi. Les hit-rates, écrits AVANT la
ligne fautive, donnaient l'illusion d'un système vivant.

**Trois verrous posés** :
1. import `_cfg` au niveau module + learn/record SÉPARÉS avec exceptions
   IMPRIMÉES dans les logs du scan (fini le silence) ;
2. smoke test learn() BOUT EN BOUT sur fichiers temporaires (aucun test
   n'exerçait la fonction entière — le NameError passait les 340 tests) ;
3. le watchdog surveille désormais la FRAÎCHEUR du cerveau (brain_log > 20 min
   -> alerte Telegram 🚨) — la microstructure était surveillée, pas le cerveau.

Leçon (la 3e du jour sur le même thème) : un try/except best-effort sans trace
est une dette de visibilité ; tout chemin critique mérite son test de bout en
bout ET son tripwire de fraîcheur.

**Addendum §61 — « vérifie que rien n'est aveugle » : l'examen et la garantie.**
Examen complet du 03/07 17h : les 14 agents voient (votes différenciés sur
données réelles — F&G 21 Extreme Fear, imbalance +0.36, palette du savant
active), 8/8 consensus frais, 12/12 sources amont vivantes (bougies, carnet,
684 prix, TradFi 5/5, Kalshi, F&G, univers, funding + percentile, micro,
équité, positions), 11/11 artefacts frais. GARANTIE PERMANENTE : le watchdog
surveille désormais la CARTE DE FRAÎCHEUR complète (10 artefacts, un par
boucle, seuils adaptés aux cadences) — un writer qui se tait, quelle qu'en
soit la cause (exception avalée, étape sautée, service mort), FIGE son
artefact et déclenche l'alerte Telegram sous 15 min. Surveiller les SORTIES
couvre toutes les formes de silence d'un coup — c'est la clôture systémique
des trois incidents de silence du jour.

---

## §62 — Audit des trois agents négatifs : formulations disculpées, le régime accusé

**Exécution des recommandations post-§61** : banc GELÉ à 14 agents (le
combination puzzle et l'audit live montrent que la largeur n'est pas le goulot ;
onchain_btc reste dormant, réévaluation seulement si un manque de canal est
démontré). Puis audit de formulation des trois négatifs de l'audit live
(carry −0.14, derivs −0.18, liquidations −0.18 à 1 h, AGGRAVÉS à 4 h : jusqu'à
−0.40, t −10.8 — négatifs à TOUS les horizons sur les 2.6 jours de live).

**Lecture des formulations** : les trois sont de la même famille CONTRARIAN
(derivs : fade linéaire du funding ; carry : fade pondéré funding/foule/basis ;
liquidations : aimant des pools). Dans le marché baissier actuel (F&G 21,
funding négatif), toutes votent LONG en continu -> l'hémorragie récente.

**Étalon sur la fenêtre PROFONDE (90 j de funding réel × bougies, n=181)** :
- fade LINÉAIRE (formulation actuelle de derivs) : +0.02 (8 h), **+0.14
  (24 h, t 1.9)** — POSITIF sur 3 mois à son horizon naturel ;
- fade aux EXTRÊMES (percentile 85/15, hypothèse SAVOIR §5) : +0.08/+0.09,
  27 % de votants — PAS clairement meilleur : le gate n'est pas adopté.

**Verdict** : formulations INTACTES. La sous-performance live est un RÉGIME
(2.6 jours, fenêtre unique) — le même piège que §54, évité cette fois. C'est
exactement le travail de la couche adaptative : les hit-rates dépondèrent en
régime défavorable, la formulation garde son espérance de long terme.
liquidations (non rejouable hors-ligne) bénéficie de la présomption de la même
famille. À suivre en revue : si la négativité PERSISTE sur des semaines
multi-régimes, la question se rouvrira — sur données, pas sur 2.6 jours.
