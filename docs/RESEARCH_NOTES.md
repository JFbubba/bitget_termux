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
