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

---

## §63 — Cadences resserrées (décision propriétaire) : scan 1 min, watchdog 5 min

Demande : « scan 14 agents toutes les minutes, watchdog toutes les 5 minutes,
récap Telegram toutes les 15 » (notify était déjà à 15 ; watchdog était à 3 —
passé à 5). Le scan passe de 5 min à 1 min (cycle ~60 s : systemd ne superpose
jamais deux instances -> cadence effective = durée du cycle). Marges API :
larges (endpoints publics 20 req/s, caches runtime inchangés).

COMPENSATIONS de constantes de temps (sans elles, la cadence ×5 aurait
dénaturé l'apprentissage) :
- BRAIN_LOG_CAP 500 -> 2400 : à 480 entrées/h (8 symboles × 60 cycles), la
  fenêtre de 500 aurait ÉVINCÉ les entrées AVANT leur maturation (1 h) —
  l'apprentissage serait mort de faim ; 2400 ≈ 5 h de fenêtre ;
- BRAIN_HITRATE_ALPHA 0.05 -> 0.01 : l'EWMA est une constante de TEMPS, pas de
  lots — même demi-vie (~14 h) qu'avant malgré des lots ×5 plus fréquents ;
- BRAIN_EARCP_LISSAGE 0.1 -> 0.02 : même vitesse horaire de convergence vers
  la cible qu'avant.

**Addendum §63 — le cerveau a son timer dédié.** Mesure post-bascule : le cycle
COMPLET de scan dure ~70-85 s (18 étapes) — un « toutes les minutes » précis
était physiquement borné. Le cerveau seul : 18 s caches chauds. Restructuration :
`bitget-brain.timer` (1 min précise, AccuracySec 10 s) exécute brain_cycle.py
seul ; le scan (boucles, veille, moniteurs) le SAUTE désormais (SKIP) et garde
sa cadence ~1 min effective. Résultat : les 14 agents votent CHAQUE minute,
sans double vote, et les boucles décident sur un consensus jamais plus vieux
que ~60 s.

## §64 — Surcouche Smart Money Concepts (SMC/ICT) : lecture seule + overlay dashboard

Demande propriétaire : intégrer les stratégies du dépôt `JFbubba/smc` (BPR, SMT
Divergence, Liquidity Sweep, Silver Bullet, Power of Three, Kill Zones, FVG,
ChoCh) et un algorithme pour les exploiter et les AFFICHER sur le graphique du
dashboard.

**Réalisation — `smc.py` (classé SAFE, PUR).** Traduction déterministe des concepts
en booléens/zones à partir d'OHLCV public : `fair_value_gaps` (3 bougies, filtre
ATR×0.5, marque le remplissage), `swings` (fractales de Bill Williams 5 bougies),
`liquidity_sweeps` (perce un swing puis réintègre en clôture), `change_of_character`
(séquence stricte sweep → cassure EN CORPS du swing responsable → déplacement
corps ≥60 % laissant un FVG), `balanced_price_ranges` (deux FVG opposés qui se
recouvrent), `kill_zone`/Silver Bullet (fenêtres heure de New York via zoneinfo,
repli UTC-4), `power_of_three` (Midnight Open + phase AMD + discount/premium),
`session_levels` (Asian H/L, PDH/PDL), `smt_divergence` (rupture de corrélation
BTC↔ETH). `analyze()` agrège en une checklist de confluence 0..4 et un `setup`
PAPER (direction/entrée/stop/tp1/tp2) avec **garde-fou géométrique** (le stop est
ancré sur le plus-bas/plus-haut RÉEL du mouvement, jamais un niveau lointain ; un
setup incohérent est marqué `coherent:false` et jamais `ready`).

**Ligne rouge respectée.** SMC n'entre PAS dans le banc des 14 agents (GELÉ §62) :
c'est une surcouche d'OBSERVATION, absente de `guards()` et de tout chemin
d'exécution. Aucune sortie ne desserre un mur argent (50/250, ×5, stop journalier,
kill-switch, porte d'edge) ni ne modifie le sizing réel. Le `setup` est un PLAN
indicatif, jamais un ordre. Les 3 portes restent vertes (tests, security_agent,
safe_push_check).

**Dashboard.** `server.py` expose `state["smc"]` (bougies dédiées profondes 150 +
paire SMT corrélée, caché 60 s, best-effort). `index.html` ajoute une couche
« SMC » (toggle dans la légende) : zones FVG (vert/rouge) et BPR (ambre) en paires
de lignes, niveaux de référence (Asian H/L, PDH/PDL, Midnight Open), marqueurs
SWEEP (rond) et ChoCh (carré) ancrés à la bougie de l'event, plus une bande texte
sous le graphe (kill zone NY, checklist de confluence, phase PO3, ligne de setup).

## §65 — Réseau neuronal de FUSION : 16ᵉ voix opt-in + carte de connectivité

Demande propriétaire : « crée un réseau neuronal complet et pertinent entre tous
les éléments du bot ». Choix explicites : **voix bornée DANS les murs** · **méta-modèle
de fusion ET carte de connectivité** · **PyTorch**.

**`neural_net.py` (SAFE, PyTorch).** MLP `[14 → 24 → 24 → 1]` (sigmoïde) qui FUSIONNE
non-linéairement les votes des 14 agents (ordre canonique = `swarm_brain.AGENTS`, gardé
par un `feature_hash` qui refuse un modèle désaligné). `vector_from_votes` est le point
où tous les éléments décisionnels convergent en une entrée. Entraîné OFFLINE sur
`brain_log.json` : étiquette = signe du rendement forward à ~15 min ; split temporel,
seed fixe (repro), early-stopping sur la validation, `BCEWithLogitsLoss` rééquilibré.
Poids sérialisés HORS git (`neural_net_weights.pt` / `_meta.json`, gitignored) — entraînés
sur le VPS. `predict()` et `connectivity_map()` sont FAIL-SAFE (torch/poids absents →
None / carte inerte, jamais d'exception).

**Honnêteté sur l'edge.** Premier entraînement : 2271 exemples, val_acc ≈ 0.51 (≈ hasard) —
5 h de données d'un seul régime pour prédire la direction à 15 min, c'est structurellement
dur et le train (0.59) > val montre le surapprentissage. **C'est exactement pourquoi la
voix ship OFF et bornée** : son edge live doit être PROUVÉ (audit IC / paper) avant tout
armement, comme tout expérimental (rampe WATCH, échelle d'edge). Le réseau se réentraîne
quand `brain_log` s'étoffe (`python neural_net.py --train`).

**`nn_agent.py` — 16ᵉ voix (strictement symétrique au LLM 15ᵉ).** Interface
`{vote, confidence, note}`, gated `NN_AGENT_ENABLED` (défaut OFF), poids fixe borné
`NN_AGENT_WEIGHT` (cap `BRAIN_WEIGHT_MAX`), confiance plafonnée `NN_AGENT_CONF_CAP`,
cachée `NN_AGENT_TTL_S`. Elle LIT les votes déjà calculés (passés en `context` par
`gather_votes` → pas de recalcul ni de récursion) et les fusionne.

**Banc gelé & murs intacts.** Câblage dans `swarm_brain` : `gather_votes` ajoute
`votes["nn"]` après le LLM (fail-safe) ; `_with_nn_weight` injecte le poids borné dans
l'agrégation SANS jamais le persister ni le soumettre à l'EARCP — `learn()` n'itère que
sur les 14 (`for k in cible`). OFF → dict à 14 voix identique à avant. La voix influence
le consensus/sizing suggéré ; elle ne touche JAMAIS `guards()` (50/250, ×5, stop,
kill-switch, porte d'edge), qui restent absolus et déterministes.

**Carte de connectivité (dashboard).** `connectivity_map()` renvoie nœuds + arêtes +
activation LIVE : les 14 agents (groupés flux/prix-structure/quant/contexte) + surcouches
(SMC §64, LLM) → cerveau → réseau de fusion → consensus → **MURS ABSOLUS** → exécution.
`state["neural"]` (réutilise le `brain` et le `smc` déjà calculés) alimente un canvas
`dessineReseau` : nœuds teintés par le vote live, le nœud « murs » distinct et verrouillé,
la voix NN cerclée selon ARMÉE/OFF, badge P(hausse) + val_acc.

**Dépendance.** PyTorch CPU installé dans le python système du bot (`pip
--break-system-packages`, wheel cpu ~2.12). Réversible (`pip uninstall torch`). Le code
dégrade fail-safe si torch venait à manquer.

## §66 — Dashboard : positions RÉELLES en cours (spot · marge iso/cross · futures)

Demande propriétaire : afficher sur le dashboard les trades en cours par catégorie.
`real_positions.py` (SAFE, lecture seule) : 4 GET SIGNÉS de consultation via le signeur
de `bitget_balance_reader` (clé Trade-only, jamais Withdraw) — `spot` (avoirs valorisés
> 1 $, poussière/coins non cotés exclus), `margin_isolated`/`margin_crossed` (par
symbole/coin, emprunt actif ou net non nul = trade en cours), `futures`
(`/api/v2/mix/position/all-position` : sens, taille, entrée, mark, PnL latent, levier,
mode de marge). `snapshot()` agrège best-effort PAR catégorie ([] + `errors` si un
endpoint échoue, jamais d'exception). Aucun ordre, aucune écriture.

Dashboard : `state["real_positions"]` (caché 30 s) alimente un panneau pleine largeur à
4 colonnes (spot / marge isolée / marge croisée / futures), en-tête avec totaux (valeur
spot, notionnel futures, uPnL). Données RÉELLES -> visibles par défaut (hors bascule
paper §65b). 3 tests (filtre poussière, parse futures, fail-safe snapshot) — 392/392 OK.

**Addendum §65b** — dashboard : graphique 230->440 px, données PAPER masquées par défaut
(bouton « Paper » ; `data-scope="paper"` + `body.hide-paper`), dynamisation (flash de
prix, point LIVE battant, transitions). `dashboard/server.py` charge le fichier
d'environnement (`load_dotenv`) pour refléter les voix opt-in LLM/NN armées en prod.

## §67 — Surfaces de trading bornées : spot libre · marge · virements · earn

Demande propriétaire : « active et utilise l'entièreté des fonctionnalités Bitget ».
Périmètre confirmé (AskUserQuestion) : toutes les surfaces, **caps relevés par paliers**
(architecture gardée), **retraits HORS-JEU** (clé Trade-only). Livraison : les briques
sont CONSTRUITES, **défaut OFF**, jamais armées de moi-même (l'armement de chaque verrou
reste une décision propriétaire explicite, comme §45).

**Noyau `bitget_execute.py` (SAFE, neutre).** Aucun mot-clé d'ordre (runner générique).
Centralise la sûreté : `gate()` (verrou LIVE env>config, défaut OFF), `kill_active()`
**fail-CLOSED** (état inconnu -> on bloque), `capped()` (cap effectif = min(env, mur
ABSOLU en dur)), `guard()` (verrou+kill+cap/op+cap/jour+solde), `run()` **DRY par défaut**
(confirm=True requis pour le réel), journal partagé `trading_real_ledger.json`.

**4 exécuteurs de surface** (chacun délègue au noyau) : `spot_trader.py` (achat/vente
spot libre), `margin_trader.py` (ordre + borrow/repay, isolée/croisée), `account_transfers.py`
(virements INTERNES, allowlist de comptes, aucune destination externe), `earn_manager.py`
(souscription/rachat). Trois verrous indépendants requis pour tout ordre réel : **verrou
LIVE armé + kill-switch absent + `--confirm`**. Vérifié : OFF -> refus ; armé sans confirm
-> DRY (aucun ordre) ; kill-switch -> refus ; cap dépassé -> refus.

**Sécurité préservée (invariant DUR).** `security_agent` audite les nouveaux fichiers :
`withdraw` INTERDIT partout (clé Trade-only), `transfer` autorisé UNIQUEMENT dans
account_transfers, délégation au noyau + confirm + gate LIVE EXIGÉS ; le noyau reste
neutre ; `trading_status.py` (statut dashboard) prouvé lecture seule (aucun verbe
d'écriture). `safe_push_check` autorise ces exécuteurs (comme spot/futures_executor). Un
test de régression bloque toute réapparition de `withdraw` dans un exécuteur. 11 tests
ajoutés (402/402 OK, 3 portes vertes).

**Dashboard.** Panneau « Surfaces de trading » (armé/OFF + caps effectifs vs absolus +
dépensé du jour), via `trading_status.snapshot()` -> `state["trading_surfaces"]`.

**Leviers (.env, défaut OFF)** : `SPOT_TRADE_LIVE`, `MARGIN_TRADE_LIVE`, `TRANSFER_LIVE`,
`EARN_LIVE` ; caps `*_MAX_PER_OP_USDT` / `*_MAX_DAILY_USDT` (relèvent SOUS le mur absolu
codé). Armer = décision propriétaire explicite, par paliers, sur exécution propre.

## §68 — Sizing par le critère de Kelly + armement des surfaces §67

Demande propriétaire : « arme tout ce qui est possible et utilise le critère de Kelly ».

**`kelly.py` (SAFE, pur).** `f = W − (1−W)/R` avec garde-fous DURS : edge négatif (f ≤ 0)
-> **mise 0** (jamais de pari à edge négatif ni de « pari inverse ») ; **demi-Kelly** par
défaut (KELLY_FRACTION=0.5) ; **plafond dur** KELLY_MAX_FRACTION=0.25 ; le montant est
ENSUITE reborné par le cap/opération de la surface (Kelly ne dimensionne qu'À LA BAISSE
dans les murs). W/R lus des stats MESURÉES (stats_report). Câblé : `--kelly` dans
spot_trader/margin_trader (source de taille), `state["kelly"]` + bandeau dashboard.

**Résultat HONNÊTE sur les stats réelles** : W=35.9 %, R=0.56 -> **f complet = −0.79**
-> f appliqué = **0** -> taille recommandée **$0 sur toutes les surfaces**. L'edge mesuré
est décisivement négatif ; Kelly ordonne de NE RIEN MISER. C'est le garde-fou qui opère :
« utiliser Kelly » ici = ne placer aucun pari tant qu'un edge positif n'est pas démontré.

**Armement §67.** Les 4 verrous LIVE (`SPOT_TRADE_LIVE`, `MARGIN_TRADE_LIVE`,
`TRANSFER_LIVE`, `EARN_LIVE`) sont ARMÉS (.env, décision propriétaire explicite). MAIS :
(1) armer ≠ trading auto — les surfaces §67 sont CLI + `--confirm` uniquement, aucune
boucle ne les déclenche ; (2) les deux autres verrous tiennent (kill-switch + `--confirm`
par ordre) ; (3) Kelly dimensionne à 0 -> même armé, un ordre Kelly-sizé est REFUSÉ
(montant ≤ 0). Vérifié : armé+Kelly -> refus ; armé+montant explicite sans confirm -> DRY.
AUCUN ordre réel n'a été placé (edge négatif). 4 tests Kelly (406/406 OK, 3 portes vertes).

## §68 (suite) — Voie saine : A (élagage live) puis B (calibration des sorties)

**A — élagage live (fait).** `_apply_watch` rendu env-aware ; `BRAIN_WATCH_AGENTS` armé
avec les 7 agents à IC live ≤ 0 (flows, divergent, orderflow, geometric, macro, carry,
technicals). Le consensus LIVE ne garde que les 7 à IC positif (derivs, leadlag,
liquidations, savant, sentiment, simons, structure) + voix opt-in llm/nn. Contrefactuel
mesuré : IC 1h +0.026 -> +0.071 (t 12.3), Kelly f -0.15 -> +0.027 (bascule positif).
Réversible, ne touche aucun mur argent.

**B — calibration des sorties (`exit_calibration.py`, mesuré).** Rejoue le chemin de prix
des 248 trades paper et cherche le SL/TP (grille ATR × RR) qui maximise l'espérance
E = W·RR − (1−W). Résultats : MFE/MAE médianes ~1.5–2.2 R (les trades oscillent large ;
le stop 1.5·ATR se fait sortir par le bruit). L'actuel (SL 1.5·ATR, RR 2) est marginalement
POSITIF en re-simulation propre (E +0.05 R/trade) — mieux que les stats réalisées (le
checker d'outcome coupe les gagnants trop tôt). **Optimum robuste (2 fenêtres 24 h/48 h) :
SL 1.5·ATR / RR 1.5** — W ~44 %, E +0.087–0.102 R/trade (~2× l'actuel). Enseignement :
**RR 2 est trop ambitieux ; prendre le profit à 1.5 R** capte les trades qui atteignent
+1.5 R puis se retournent. Advisory : appliquer = décision mandat (RR 2 -> 1.5).

## §68 (fin) — Réalignement des poids EARCP sur l'IC live (fin de la béquille WATCH)

Cause racine mesurée (§68/§51) : les poids EARCP anti-corrélaient avec la prédictivité
(flows pesait 1.33 pour un IC live −0.03 ; sentiment 0.88 pour un IC +0.10). L'élagage
WATCH (7 agents à 0) était une béquille ; on la remplace par un pilotage PRINCIPIEL.

`_apply_ic_alignment(weights)` (jumeau de `_apply_edge_priors`) : poids × mult**alpha,
normalisé, re-borné [0.2,3.0]. `mult = clamp(1 + IC/scale, 0.25, 2.5)` (scale 0.05) tiré de
l'IC live (`live_ic_audit`, ~30k votes, caché ~1×/h). Appliqué dans `learn()` après les
edge-priors -> réaligne les poids PERSISTÉS. Gated `BRAIN_IC_ALIGN` (env prioritaire,
défaut OFF), fail-safe neutre. Effet mesuré (poids avant -> après) : flows 1.47->0.35,
orderflow 1.01->0.48, macro 1.58->1.04 ; sentiment 0.88->1.41, liquidations 1.83->2.70,
derivs 1.81->2.61, leadlag 0.89->1.34. Le poids suit désormais l'IC mesuré.

Activation : one-shot pour réaligner les poids persistés immédiatement (ferme le gap),
`BRAIN_IC_ALIGN=1`, et `BRAIN_WATCH_AGENTS` RETIRÉ — les 14 agents votent à nouveau, les
faibles-IC simplement down-weightés (principiel) au lieu d'être zérotés. Réversible
(BRAIN_IC_ALIGN=0). Banc gelé à 14 intact (§62) : on réaligne la pondération, pas la
composition. 1 test (409/409 OK, 3 portes vertes).

## §68 (addendum) — Plancher EARCP : mélange géométrique (fin de la saturation)

Défaut détecté après le §68 : l'IC-align MULTIPLICATIF (poids × cible^α) SATURAIT — top
agents collés au plafond 3.0, bas au plancher 0.2 (retour du §51). Et un agent à IC positif
déjà au plancher (simons IC +0.031 votants 97.7 %, savant +0.029) NE remontait pas : la
normalisation, dominée par les tops, le repoussait sous 0.2.

Fix : **mélange GÉOMÉTRIQUE vers la cible IC** — `w^(1-α)·cible^α` (α=0.85 défaut, env-aware
`BRAIN_IC_ALIGN_ALPHA`). Un agent planché est TIRÉ vers sa cible IC (w^0.15 ≈ 1) au lieu d'y
rester collé. Mesuré (poids persistés après) : simons 0.20 -> 0.92, savant 0.20 -> 0.90 ;
tops sentiment/liquidations/derivs ~1.9 (PLUS de plafond) ; flows/divergent ~0.26 (IC
négatif). AUCUN agent au plancher/plafond -> distribution IC-alignée saine. Réversible
(BRAIN_IC_ALIGN_ALPHA plus bas = plus d'EARCP appris ; =1 = cible IC pure). 409/409, portes vertes.

## §69 — Optimisation du dashboard : latence /api/state 22 s -> 5 s (froid), 2 s -> 0.01 s (chaud)

Mesure : le build de l'état était une SOMME séquentielle d'appels réseau/signés (froid
22.7 s). Deux corrections :
  1. **kelly dédupliqué** (le pire, 4.13 s) : `kelly.snapshot()` re-fetchait real_positions
     (4 GET signés) + futures_report via `account_capital` — DUPLIQUANT l'état déjà calculé.
     Le dashboard lui INJECTE désormais capital (real_positions+futures_live) et W/R (stats)
     -> kelly ne fetch plus rien (~4 s -> ~0).
  2. **`_prewarm` parallèle** : tous les producteurs INDÉPENDANTS (brain, futures, liq,
     orderflow, accum, realpos, smc, viz, macro, …) sont pré-calculés dans un
     ThreadPoolExecutor (8 workers) avant l'assemblage -> latence = MAX au lieu de SOMME.
     `_cached` rendu thread-safe (verrou, calcul HORS verrou). Les producteurs DÉPENDANTS
     (projection/future/neural/kelly) restent séquentiels après (lisent brain/smc/…).
Résultat : froid 22.7 s -> 5.5 s, chaud 2.0 s -> 0.01 s (mesuré live : 5.4 s / 0.04 s).
Payload inchangé (37 Ko), données identiques. Front : polling ADAPTATIF (suspendu quand
l'onglet est masqué, refresh immédiat au retour) -> économise VPS + navigateur. 409/409, portes vertes.

## §69 (suite) — /api/state INCRÉMENTAL : delta versionné (37 Ko -> ~0.5 Ko/poll)

Le poll renvoyait les 37 Ko complets toutes les 5 s alors que la plupart des 39 clés ne
changent pas. Modèle DELTA versionné : `build_delta(symbol, tf, since)` construit l'état
complet (cache chaud ~0.04 s), verse une version MONOTONE à chaque clé qui change, et
renvoie soit FULL {v, state} (curseur absent/invalide/postérieur -> client neuf, changement
de symbole, redémarrage serveur), soit DELTA {v, changed} (uniquement les clés de version >
since). Stateless & multi-clients : versions côté serveur par symbole:tf, le client ne porte
qu'un curseur entier. Front : `_stateV` fusionne les deltas dans `window._ST` (reset -> full
au changement de symbole/TF), rendu depuis l'état fusionné. Rétro-compatible (sans `since` =
full). Mesuré live : full 38.7 Ko -> delta 583 o (juste timestamp + orderbook), jusqu'à ~400×
en régime stable. 409/409, portes vertes.

## §69 (fin) — Poll -> PUSH SSE : le serveur pousse les deltas (plus de boucle de fetch)

`/api/stream` (Server-Sent Events) : une connexion persistante par client (thread dédié
via ThreadingHTTPServer). Envoie un FULL puis des DELTAS versionnés (build_delta) à cadence
fixe (DASH_SSE_INTERVAL, défaut 2 s) ; à la déconnexion l'écriture lève -> le thread se
termine proprement. Front refactoré : `renderState()` (rendu depuis window._ST) séparé de la
source ; `applyDelta()` (fusion + rendu) commun à SSE et poll ; `EventSource` en primaire,
POLL `/api/state` en REPLI (navigateur sans SSE ou échec). Reconnexion au changement de
symbole/TF (URL SSE figée) et à la reprise de visibilité ; coupe le flux quand l'onglet est
masqué. Mesuré live : FULL 38.7 Ko (1×) puis deltas 250-622 o toutes les 2 s. Rétro-compatible
(/api/state poll conservé). 409/409, portes vertes.

## §68 (audit boucle) — Auto-amélioration : ce qui tourne, le fix source, le moniteur, les timers

Audit runtime : la boucle EARCP tourne (brain 1 min, validation 6 h, revue hebdo, artefacts
frais, 1887/2400 évaluées) MAIS son signal de base est cassé — corrélation de rang
**hit-rate ↔ IC = ~0** (geometric hit-rate 0.71 / IC 0.000 ; derivs hit-rate 0.32 / IC +0.061).
Le NN ne se ré-entraînait PAS (manuel), et evolution/strategy_lab n'étaient PLANIFIÉS nulle part.

Corrections :
  • **Fix À LA SOURCE** : l'IC-align déplacé des poids finaux vers la CIBLE EARCP dans
    `learn()` (`cible = _apply_ic_alignment(cible)`) — l'IC pilote la cible d'apprentissage,
    le lissage y converge (plus un patch après coup). Mesuré : corr POIDS APPRIS ↔ IC = **+0.69**.
  • **Moniteur `learning_health.py`** : corr de rang poids-appris ↔ IC (doit être ≥ 0.2) +
    corr hit-rate ↔ IC (cause racine). Alerte Telegram si les poids décrochent de l'IC
    (le correctif ne compense plus / BRAIN_IC_ALIGN OFF).
  • **Timers manquants** (`deploy/install_learning_timers.sh`, à lancer par le propriétaire —
    la persistance planifiée n'est pas créée par l'agent) : `bitget-neural-train` (NN quotidien
    04:20), `bitget-strategy-lab` (sep-CMA-ES hebdo dim 05:00), `bitget-learning-health` (6 h).
Tout lecture seule / entraînement offline, aucun ordre. 410/410, portes vertes.

## §70 — Révision générale : NN honnête (données + split), halte MDD fantôme visible + réancrage, DCA un jour sur deux corrigé

Revue complète du bot (06/07 après-midi). Quatre problèmes réels trouvés et traités.

**1. Le réseau de fusion s'entraînait sur les mauvaises données avec un split fuyant.**
`neural_net.py --train` lisait `brain_log.json` (fenêtre courte : 2 271 exemples ≈ 5 h)
alors que `brain_log_history.jsonl` offrait 31 574 lignes sur 3 jours — et le timer
quotidien (§68) promettait déjà « sur brain_log_history ». Pire : le split de validation
coupait la queue de la liste GROUPÉE PAR SYMBOLE — train et val couvraient la même période
sur des symboles corrélés (fuite transversale) ; le val_acc 0.5066 (v1) était un artefact.
Refonte : lecture historique JSONL (repli brain_log.json), échantillons TRIÉS PAR TEMPS
GLOBAL, split temporel PURGÉ (les exemples de train dont la fenêtre d'étiquette mord sur
la validation sont retirés), deadband anti-bruit (|ret| < 5 bps ignoré, NN_DEADBAND),
tolérance de trou (étiquette au-delà de horizon+600 s ignorée), mini-batches + dropout
0.15 + early-stopping (patience 60), et métriques honnêtes : Brier, TAUX DE BASE
(prédicteur constant), précision haute-confiance (|p−0.5| ≥ 0.10).
**Résultat honnête : PAS d'edge hors-échantillon.** Grille horizon (900/1800/3600/7200 s)
× deadband (5/10/20 bps) sur 3 j de données : val_acc 0.38–0.52, TOUJOURS sous le taux de
base (0.57–0.71) ; zéro prédiction haute-conviction. Le méta-modèle n'apprend rien
d'exploitable sur 3 jours — il faut plus de profondeur (le journal grandit, le cron
quotidien ré-entraîne). Conséquence défensive : **porte d'edge de la 16ᵉ voix** —
`nn_agent` lit `val_edge` (val_acc − base) du dernier entraînement et SE TAIT
(vote 0, conf 0, note `nn:sans-edge`) tant qu'il n'est pas positif. Même philosophie que
Kelly=0 sur edge négatif (§68). Méta enrichie (arch, deadband, fenêtre de données,
trained_at) + garde `arch` au chargement (poids désalignés -> None, fail-safe).

**2. Halte drawdown FANTÔME : la boucle futures était gelée en silence depuis le 05/07 17:41.**
L'equity du livre est passée de ~402 à ~240 $ le 05/07 au soir — PAS une perte de trading
(PnL bot NET −0.10 $ sur 25 fills) mais un MOUVEMENT DE CAPITAL hors du livre piloté.
La garde 6 (`mandate.drawdown_halt` sur `equity_curve()`) ne distingue pas un virement
d'une perte -> halte 40.45 % ≥ 20 %, 208 refus journalisés, et `drawdown_from_peak`
prend le MAX sur la fenêtre (~7 j de points intrajournaliers) : la halte ne se lève pas
d'elle-même, même si les fonds reviennent. Double angle mort : `futures_report` et
`futures_auto --status` affichaient « ARMÉE · OUVRIR long » sans mentionner la halte.
Corrections : `futures_executor.drawdown_status()` (lecture seule) affiché PARTOUT
(bandeau 🛑 dans futures_report + futures_auto --status quand halt) ; et OUTIL
PROPRIÉTAIRE `python futures_executor.py --rebase-equity` (DRY par défaut, `--confirm`
pour agir) : réancre la courbe intrajournalière au point courant, journalise l'état
remplacé (`FUTURES_EQUITY_REBASE`, traçable), refuse si equity illisible (fail-closed).
AUCUNE auto-levée : le réancrage reste une décision explicite du propriétaire (règle 2).
La halte est TOUJOURS ACTIVE à l'heure de cette note — décision propriétaire attendue.

**3. Le « DCA quotidien » achetait UN JOUR SUR DEUX (gigue de 3 secondes).**
Achats réels : 30/06 12:00:03 · 01/07 12:00:04 · 02/07 12:00:04 · 04/07 12:00:04 —
03/07 et 05/07 SAUTÉS. Le cron tire à 12:00:01, l'achat est horodaté ~12:00:04 (latence
ordre), donc au cycle suivant 23 h 59 min 57 s < 24 h -> « intervalle non écoulé ».
Fix : `should_buy(..., slack_s=300)` — tolérance 5 min sur l'intervalle (jamais deux
achats le même jour : 23 h 55 reste l'espacement minimal). Test de non-régression ajouté.

**4. Divers.** BrokenPipeError récurrent du dashboard silencié dans `_send` (client parti
en cours de réponse = normal, le chemin SSE l'attrapait déjà). ROADMAP « Interdit »
réconcilié avec l'état §67 (surfaces bornées armées le 06/07 : vente spot/marge/virements/
earn possibles UNIQUEMENT via CLI --confirm avec caps, jamais en boucle auto ; RETRAIT
interdit partout). Vérifié : les boucles §68 sont planifiées via CRONTAB (installé 08:13)
— neural-train 04:20, strategy-lab dim 05:00, learning-health 6 h — premières échéances à
venir ; ne PAS doubler avec les timers systemd de `deploy/install_learning_timers.sh`.

## §71 — Réseau de fusion v3 : features contextuelles causales, antisymétrie, ensemble, walk-forward

Amélioration du méta-modèle (§65/§70) sur quatre axes, avec verdict MESURÉ à chaque pas.

**1. Features (14 -> 23).** Les 14 votes seuls ne suffisaient pas (edge −0.07 au §70).
Ajout de 9 contextuelles STRICTEMENT CAUSALES (`EXTRA_FEATURES`, calculées à l'identique
à l'entraînement — fenêtre passée du dataset — et à l'inférence — queue de brain_log.json,
fail-safe zéros) : agrégats du banc (moyenne, dispersion, accord de signe, delta de
consensus 15 min), dynamique du symbole (rendement 15/60 min et vol 60 min, échelles
fixes RET_SCALE/VOL_SCALE), saisonnalité intra-jour (heure UTC sin/cos). `feature_hash`
couvre désormais banc + contextuelles.

**2. Prior d'antisymétrie.** Le logit est g(x) − g(x·flip) où flip renverse les features
DIRECTIONNELLES (votes, rendements, deltas) et préserve le CONTEXTE (vol, dispersion,
heure) : renverser tous les signaux directionnels renverse EXACTEMENT la prédiction
(propriété testée à 1e-6). Divise l'espace à apprendre par deux. Mesuré meilleur que le
MLP simple à hidden=32 (wf_edge +0.004 vs −0.010).

**3. Ensemble de graines (×3).** Trois réseaux (SEED, +1, +2), sigmoïdes MOYENNÉES.
Première conséquence visible : le modèle ose enfin des prédictions à haute conviction
(212 sur la fenêtre finale, précision 0.604) là où v2 n'en produisait AUCUNE.

**4. Walk-forward (4 plis) = l'edge qu'on gate.** Un split unique dépend du hasard de SA
fenêtre (base 0.57-0.71 selon la fenêtre, §70). Désormais : 4 fenêtres de validation
consécutives, chacune prédite par un modèle entraîné sur son seul passé (purge anti-fuite
par pli). La 16e voix gate la BORNE PRUDENTE wf_edge − se (erreur-type inter-plis) —
un +0.004 moyen sur des plis à ±0.08 est du bruit, pas un edge.

**Verdict v3 (23 674 exemples, 3 j) : MIEUX mais toujours PAS d'edge démontré.**
wf_acc 0.548 vs base 0.547 (edge moyen +0.0015, se 0.035 -> borne prudente −0.033) ;
plis : +0.022, +0.006, +0.085, −0.107. Le pli 2 montre une vraie poche de prédictibilité
(+0.08-0.09 sur TOUTES les configs) ; le pli 3 (marché en tendance, base 0.59) reste
imprévisible pour le modèle. La 16e voix reste donc MUETTE (note `nn:sans-edge(-0.033)`),
par construction, jusqu'à ce que le journal accumule assez de profondeur pour que la
borne prudente passe positive. Le cron 04:20 réentraîne chaque jour sur un journal qui
grandit (~13 k lignes/j) — la décision se prendra sur les chiffres, pas sur l'espoir.
Sérialisation : {models: [state_dicts]} + méta enrichie (arch_v=3, in_dim, antisym,
n_models, wf complet) ; garde arch_v au chargement (poids v2 -> None, fail-safe).

## §71 (suite) — 16e voix ARMÉE : porte d'edge automatique + alerte d'ouverture

Décision propriétaire (06/07 après-midi) : la 16e voix doit PARLER dès que l'edge
devient positif. État câblé :
  • `NN_AGENT_ENABLED=1` (levier env, armé par le propriétaire) — le cerveau consulte
    la voix à CHAQUE cycle (`votes["nn"]`, poids fixe borné NN_AGENT_WEIGHT, EARCP
    intact §62) ;
  • la PORTE D'EDGE décide seule de la parole, automatiquement, à chaque réentraînement
    quotidien (cron 04:20) : critère configurable `NN_EDGE_GATE` — `prudent` (défaut :
    wf_edge − erreur-type inter-plis > 0) ou `brut` (wf_edge moyen > 0, assume le bruit) ;
  • ALERTE TELEGRAM à la TRANSITION (train() -> _notify_gate_transition) : le propriétaire
    apprend le jour exact où la voix s'ouvre (ou se referme), sans surveiller les métas ;
  • PAS de boucle de rétroaction : `_record` ne journalise que le banc gelé
    (`n in AGENT_FUNCS`) -> la voix ne s'entraîne jamais sur sa propre sortie.
État au moment de la note : enabled=True, mode=prudent, edge prudent −0.033 -> la voix
est consultée mais MUETTE (`nn:sans-edge(-0.033,prudent)`). Elle s'ouvrira d'elle-même
sur chiffres. Murs argent inchangés : la voix influence le consensus, jamais guards().

## §71 (fin) — Décision propriétaire : porte d'edge en mode BRUT

Le propriétaire a basculé `NN_EDGE_GATE=brut` (levier env, 06/07 après-midi) : la 16e
voix parle dès que la MOYENNE walk-forward est positive (+0.0015 au moment du passage),
en assumant explicitement le bruit statistique (se ±0.035). Vérifié live : `nn v3`
présent dans les voix du cerveau (peek), confiance plafonnée NN_AGENT_CONF_CAP, poids
fixe borné. Raccords faits dans la foulée : l'ALERTE de transition suit désormais le
critère CONFIGURÉ (prudent/brut — elle annonce l'état de la porte qui gouverne
réellement la voix), et la CLI charge dotenv (comme brain_cycle) pour que le cron
04:20 voie les leviers env. Repasser en `prudent` = une ligne du levier env, effet au
cycle suivant. Les murs argent restent hors d'atteinte de la voix (guards() absolu).

## §72 — Les 10 algorithmes classiques : intégrés là où ils manquent, sans toucher au banc gelé

Demande propriétaire : intégrer les 10 algos classiques (MA cross, RSI, Bollinger,
MACD, grille, DCA dynamique, VWAP, pairs z-score, Donchian, Random Forest) aux
stratégies/agents appropriés. Inventaire préalable EXHAUSTIF (agent d'exploration) :

  DÉJÀ LIVE : n°1 EMA-cross (agent technicals, EMA20/50 ±0.5) · n°2 RSI (agent
  technicals, 35/65 ±0.3) · n°6 DCA opportuniste §44 · n°8 cousins z-score
  (simons/carry/leadlag). DÉJÀ AU LAB : n°1-4, n°9 (strat_ema_cross, strat_rsi_
  reversion, strat_bollinger, strat_macd, strat_donchian + familles CMA-ES).
  MANQUAIENT : n°5 grille (nulle part), n°7 VWAP (calculé, jamais voté), n°8 vrai
  pairs 2-actifs, n°10 RF (sklearn absent), n°6 modulation par coût moyen.

Intégrations (chaque ajout dans le style causal du lab, signal[i] = passé seul) :
  • **Laboratoire** (`strategy_lab.py`) : + `strat_vwap` (VWAP roulant, bande morte
    0.2 %), + `strat_grid` (grille de range CAUSALE : barreaux bas/hauts, se COUPE
    en tendance drift>0.35), + `strat_pairs` (z-score du spread LOG vs référence
    corrélée, alignement par ts ou index, inerte sans référence), + `strat_random_
    forest` (RF scikit-learn, refit périodique sur le SEUL passé — le « fit puis
    predict sur le même X » du folklore est du surapprentissage, pas ici ;
    déterministe, inerte sans sklearn). Familles CMA-ES `vwap`/`grid` ajoutées ;
    registre + build_named + run() étendus ; pairs choisit sa référence par symbole
    (ETH pour BTC, BTC pour le reste). scikit-learn installé (requirements-optional).
    Le cron dimanche 05:00 mesure tout ça (Sharpe/edge/PBO/promotion) — inchangé.
  • **Agent technicals (banc, n°7)** : terme VWAP ±0.2 (bande morte 0.2 %) — le champ
    `vwap` était déjà calculé par technicals.technicals(), coût zéro, EMA-cross ±0.5
    reste dominant. L'IC live de l'agent (live_ic_audit) jugera l'apport.
  • **17ᵉ voix `classics_agent.py` (opt-in, DÉFAUT OFF)** : fusion AU DERNIER PAS des
    6 classiques que le banc ne vote pas (MACD, Bollinger, Donchian, VWAP, grille,
    pairs) — moyenne des signaux {-1,0,1} (l'accord porte la conviction), confiance
    plafonnée CLASSICS_AGENT_CONF_CAP 0.5, poids fixe borné CLASSICS_AGENT_WEIGHT 0.5
    (jamais persisté, exclu du journal d'apprentissage comme llm/nn -> banc gelé §62
    intact), cache 60 s/symbole, fail-safe total. Câblée dans gather_votes +
    _with_classics_weight (peek/read), motif STRICTEMENT identique aux voix 15/16.
    Smoke réel ETHUSDT : vote 0.333 (macd+ grid+), note lisible.
  • **DCA dynamique (n°6, opt-in ACCUM_DCA_COSTBASIS, DÉFAUT OFF)** :
    `costbasis_multiplier` (≤−20 % -> ×2.5 · ≤−10 % -> ×1.5 · ≥+10 % -> ×0.5,
    fail-safe ×1) sur l'écart au PRIX DE REVIENT RÉEL (accum_reconcile : VWAP des
    fills appariés, caché 15 min) en réel, au avg_price du registre en paper. Le
    montant re-CLAMPE toujours au cap réel (ACCUM_REAL_MAX_PER_BUY_USDT) : le
    multiplicateur ne perce JAMAIS un plafond — en pratique il RÉDUIT en profit
    (×0.5) et sature au cap en drawdown. Armer = décision propriétaire.

Rien n'est armé par cette passe : les leviers CLASSICS_AGENT_ENABLED et
ACCUM_DCA_COSTBASIS restent OFF (les armer = une ligne du levier env chacun).
Le n°10 (RF) reste un instrument de MESURE au lab — pas de voix live (coût par
cycle prohibitif et philosophie : promotion sur chiffres uniquement).

## §74 — Dashboard : RÉEL uniquement, fenêtre de trades vivante, cartes animées, alignements

Demande propriétaire (06/07 soir). Quatre chantiers, dans la continuité data-viz §69 :
  • **RÉEL uniquement** : le bouton « Paper affiché/masqué » et TOUT l'affichage paper
    disparaissent (panneaux « Positions en cours (paper) », « Issues des signaux »,
    « Labo xs paper », lignes cumul paper / carry paper, tuile win-rate paper du
    bandeau). Le panneau « Wallet · Performance » (stats de signaux paper) devient
    **« Performance RÉELLE »** : PnL net bot futures en héros (fills réels, frais
    déduits), chips WIN RÉEL (Kelly W mesuré) / PAYOFF R / FILLS / FRAIS, equity
    futures, BTC accumulé réel. Bandeau : tuile « RÉEL PNL BOT ». Pied de page :
    fills réels + positions ouvertes (plus de compte de signaux fictifs).
  • **Fenêtre TRADES RÉELS EN COURS** (pleine largeur, sous le bandeau) : une ligne
    par position futures ouverte — sens (badge ▲ LONG/▼ SHORT), taille, entrée, mark,
    uPnL $ (FLASH vert/rouge à chaque variation), uPnL % (vs marge), levier·mode,
    marge, notionnel ; uPnL total dans le titre ; état FLAT explicite. Fraîcheur :
    cache serveur realpos 30 s -> 10 s (positions poussées par SSE ~2 s). La ligne
    d'entrée RÉELLE de la position du symbole s'affiche sur le graphe (remplace les
    lignes paper).
  • **Réseau de neurones ANIMÉ** (`dessineReseau` -> boucle RAF `_nnDraw`) : particules
    circulant le long des arêtes (données -> cerveau -> fusion -> consensus -> murs ->
    exécution), débit et vitesse ∝ |activation| de la source, couleur = signe ;
    activations LISSÉES (lerp) entre deux pushs SSE ; nœuds qui « respirent » avec
    leur activation (+ halo lent constant sur les murs 🔒) ; badge enrichi (edge de la
    porte). `prefers-reduced-motion` -> rendu statique (inchangé).
  • **Carte de consensus ANIMÉE** (MiroFish) : amplitudes LISSÉES (lerp, les rayons ne
    sautent plus), dérive orbitale lente (1 tour ≈ 5 min), arêtes en tirets qui
    MARCHENT vers le centre (vitesse ∝ |consensus|), cœur « MARCHÉ » qui respire avec
    |net| + onde émise quand le net est directionnel ; anneau de seuil pulsé conservé.
  • **Alignements** : la fenêtre trades partage UNE grille entre en-tête et lignes
    (alignement données/titres garanti par construction) ; `.row` cale sa valeur à
    droite ; valeurs des positions réelles en nowrap.
Vérifié : purge paper totale (0 occurrence), syntaxe JS validée (node --check),
healthz 200, /api/state expose tout ce que le front consomme. Lecture seule inchangée.

## §73 — Réseau de fusion v4 : hygiène par volatilité, calibration, et PRÉ-ENTRAÎNEMENT sur 6 ans de votes rejoués

Deux étages d'amélioration, chacun MESURÉ (walk-forward 6 plis sur le journal live).

**Étage 1 — hygiène v2 + calibration.**
  • Deadband ÉCHELONNÉ PAR VOLATILITÉ : seuil = max(5 bps, 0.35 × vol des rendements-
    horizon du SYMBOLE), vol estimée CAUSALEMENT (uniquement les rendements dont la
    fenêtre est close à l'instant t). 5 bps fixes gardaient tout le bruit de XAUT et
    n'en retiraient rien à DOGE.
  • POIDS d'exemples = |ret|/vol borné [0.25, 4] (train seul — la validation reste non
    pondérée) : un mouvement de 3σ enseigne plus qu'un frémissement.
  • CALIBRATION en température (Platt 1 paramètre, ajustée sur la validation) sur le
    LOGIT d'ensemble : T mesuré 1.14 (scratch) puis 1.92 (v4) — le réseau était
    SUR-confiant, la confiance de la 16e voix devient une probabilité honnête.
  • 6 plis (au lieu de 4), ensemble ×5 (logits moyennés), _fit/_purged factorisés.

**Étage 2 — PRÉ-ENTRAÎNEMENT sur votes REJOUÉS (la vraie profondeur).**
Le journal live n'a que des jours ; l'historique §54 a des ANNÉES. 6 des 14 voix ont
une forme PURE canonique rejouable : technicals (formule exacte d'agent_technicals,
VWAP §72 compris), divergent, simons/savant/geometric (stride 48/6/6 + tenue, à
l'image de leur lenteur live), leadlag (fade BTC). `--pretrain` reconstruit
118 309 exemples (2020-10 -> 2026-07, 4 symboles 1h, ~9.9 ms/barre), entraîne
l'ensemble (horizon 1 barre, même hygiène vol) et sérialise
`neural_net_pretrained.pt` ; `--train` s'en sert comme INITIALISATION (fine-tuning,
NN_PRETRAIN=off pour repartir de zéro). Corpus rejoué lui-même : edge ≈ 0 (−0.006) —
l'init est un PRIOR NEUTRE bien régularisé, pas une boule de cristal.

**Verdict mesuré (mêmes 6 fenêtres live)** :
  scratch  : wf_edge −0.0245 (acc 0.524)
  fine-tune: wf_edge −0.0079 (acc 0.538) — 5 plis sur 6 meilleurs -> ADOPTÉ (v4).
L'edge moyen reste ≤ 0 : la 16e voix se TAIT de nouveau (porte brut, choix
propriétaire §71 fin — `nn:sans-edge(-0.008,brut)`), et c'est exactement le
comportement voulu : elle parle sur chiffres, se tait sur chiffres. Haute-conviction :
52 prédictions à 0.596 vs base 0.565. Le cron 04:20 fine-tune désormais chaque jour
depuis le prior 6 ans sur un journal live qui grandit. (Re-pré-entraîner de temps en
temps : `python neural_net.py --pretrain`, ~35 min offline.)

## §75 — Croisement de données : funding + sentiment dans le rejeu, ctx journalisé, stratégie croisée

Demande propriétaire (06/07 soir) : ajouter funding et sentiment à l'historique rejoué,
chercher d'autres edges, améliorer le croisement de données.

**1. Profondeur de données.** Fear&Greed COMPLET (alternative.me limit=0) : 3 074 points
quotidiens 2018-02 -> aujourd'hui (`sentiment_index.download_history/load_history`,
data_history/FEAR_GREED.json, gitignored). Funding Bitget : l'API publique ne sert que
~90 jours (270 taux/symbole, testé pageNo>3 vide) — téléchargé pour BTC/ETH/SOL/XRP ;
le cron peut le consolider dans le temps (download déduplique).

**2. Rejeu v2 : 6 -> 10 voix sur 14.** Ajoutés au corpus de pré-entraînement :
  • sentiment — (50−F&G)/50 par jour, couverture TOTALE du corpus 6 ans ;
  • structure — réplique EXACTE d'agent_structure (BOS/CHoCH+piège, Value Area,
    chandeliers ; 0.1 ms/barre, aucun stride nécessaire) ;
  • derivs — −funding×2000 (funding Bitget du symbole ; 0 avant avril 2026) ;
  • carry — signal pur (composante funding-z, poids renormalisés — la dégradation
    propre du module fait le travail).
  Restent à 0 : orderflow, macro, liquidations, flows (aucune donnée historique de
  carnet/OI/macro). Coût mesuré : 5.1 ms/barre (corpus complet ~16 min).

**3. Croisement journalisé (le cœur de la demande).** `swarm_brain._record` ajoute
`ctx = {fund, fg}` à CHAQUE entrée du journal — repris des caches du MÊME cycle via
`_peek_cache` (un fetch qui lève -> stale-while-error : lecture SANS écriture, aucun
risque d'empoisonner le cache des agents, testé) : zéro appel réseau ajouté. Le NN
gagne 2 features de croisement (23 -> 25) : `funding_lvl` (funding×2000 clampé) et
`fg_dev` ((50−F&G)/50), DIRECTIONNELLES sous l'antisymétrie. Les votes derivs/sentiment
portent déjà le SIGNE contrarian ; le ctx donne l'AMPLEUR BRUTE — c'est l'interaction
votes × niveaux que le méta-modèle peut exploiter. Rétro-compatible : entrées
anciennes sans ctx -> 0 (fail-safe). Vérifié live : 30/30 dernières entrées avec ctx.

**4. Stratégie CROISÉE au lab + 17e voix.** `strat_funding_fade` (fundfade_{SYM}_60) :
foule très longue (z-funding ≥ 1.5) ET prix au plafond du range -> short le crowding ;
symétrique au plancher. Causal (pointeur funding par ts), inerte sans données. Ajoutée
au registre du lab (mesure dimanche : Sharpe/edge/PBO) ET comme 7e composant de la
voix classics armée (fail-safe 0 sur les symboles sans funding local).

## §75 (suite) — Revue de santé + fix : candidats infaisables écartés à la décision

Revue 12 h (agent d'exploration) : ZÉRO erreur sur les 6 services, 11/11 artefacts
frais, 5/5 registres intègres, halte MDD non, reconcile accumulation ok. Deux
trouvailles actionnables :
  • **Boucle directionnelle flat en boucle sur « taille infaisable »** : 3 refus réels
    journalisés (ETH ×2 le 05/07, LAB le 06/07) — la boucle choisissait le candidat au
    meilleur consensus SANS vérifier les minima du contrat (minTradeNum × prix >
    notional configuré 10 $), l'exécuteur refusait (fail-closed correct), et la place
    n'allait jamais au candidat suivant. FIX : `_taille_faisable` (juge = le même
    `size_for` que l'exécuteur, spec cachée 24 h, prix du journal du cerveau) filtre
    À LA DÉCISION dans le cycle ET le statut ; les écartés sont VISIBLES (rapport +
    clé `infaisables`) avec le remède : monter FUTURES_AUTO_NOTIONAL_USDT = décision
    propriétaire. Fail-open si spec/prix illisibles (l'exécuteur reste le juge final).
    Vérifié live : LABUSDT écarté, affiché.
  • **Libellé equity clarifié** dans futures_report (wallet futures vs livre couvert :
    l'écart ~34 $ = l'expo BTC spot du carry, pas une anomalie).
Le run d'accumulation de 12:00 est le premier à exercer la tolérance de gigue (§70)
et le DCA dynamique (§72) en production — vérifié à chaud (voir addendum).

## §75 (fin) — Mesures : rejeu v2, fine-tune v5, et la première empreinte du croisement

Corpus rejoué v2 (10 voix + ctx, 118 309 exemples) : edge −0.0052 (v1 6 voix : −0.0063)
— toujours ≈ 0 à l'heure, le prior reste un régularisateur de géométrie, pas un oracle.
Fine-tune de production v5 (25 features, prior v2) sur le journal live :
  wf_edge −0.0139 (v4 : −0.0079 — même bruit ±0.026, fenêtres légèrement décalées,
  le pli 2 reste imprévisible : −0.127) ; MAIS la POCHE HAUTE-CONVICTION fait un bond :
  **193 prédictions à 0.642 vs base 0.548 (≈ +2.6σ)** — c'était 52 à 0.596 avant le
  croisement funding/F&G. Première empreinte mesurable du ctx : le modèle ose plus
  souvent ET plus juste quand les niveaux de marché confirment les votes. À suivre
  jour après jour (le ctx ne couvre que ~1 h de journal au moment de la mesure — il
  s'épaissit à chaque cycle). La 16e voix reste MUETTE (porte brut : −0.014 ≤ 0).
Vérifications en production le même jour : achat 12:00 passé (8e, 3.21 $ ∝ score 0.403,
multiplicateur coût-moyen ×1.0 en zone neutre — §70 et §72 exercés sans accroc) ;
filtre d'infaisabilité actif (LAB écarté à la décision). 422/422, portes vertes.

## §76 — Gestion autonome des outils Bitget : notional monté, liquidité automatisée

Trois décisions propriétaires (06/07 après-midi), câblées DANS les murs :

**1. FUTURES_AUTO_NOTIONAL_USDT : 10 -> 25 $** (env-aware désormais, comme
FUTURES_AUTO_RR). Minima MESURÉS sur l'univers : ETH 17.37 · LAB 16.61 · XAUT 41.47,
le reste ≤ 8 $. À 25 $ : tout faisable SAUF XAUT (écarté-mais-visible par le filtre
§75 ; l'inclure demanderait ~45 $ — décision propriétaire future). Marge vs murs :
3 positions × 25 = 75 $ brut ≤ cap 200 ; risque/trade au SL 1.5 % ≈ 0.38 $.
Vérifié live : LAB redevenu candidat (« OUVRIR long LABUSDT »).

**2. `liquidity_manager.py` (§76) — la liquidité s'auto-gère, BORNÉE.** Module de
DÉCISION (classé à part par security_agent — scanner dédié : aucun vocabulaire
d'écriture directe, délégation OBLIGATOIRE — et par safe_push_check) qui délègue
TOUTE exécution aux surfaces §67 auditées (account_transfers, earn_manager : verrous
LIVE, kill-switch fail-closed, caps 25 $/op · 100 $/j). Politique (PURE, testée) —
UNE action par cycle, montants [5 $, cap/op] :
  marge futures < 40 $ -> virement spot->futures (si le spot garde son plancher 15 $),
    sinon rachat Earn d'abord ; float spot < 15 $ -> rachat Earn ; float spot > 120 $
    -> souscription Earn du surplus (l'argent ne dort pas) ; sinon RIEN.
  Fail-closed sur soldes illisibles ; pas de micro-mouvements (< 5 $) ; journal
  .liquidity_journal.jsonl + Telegram sur action ; gate LIQUIDITY_AUTO (défaut OFF
  dans le code, ARMÉ par le propriétaire) ; cron horaire (:15). Le RETRAIT externe
  reste impossible partout (clé Trade-only). Seuils env : LIQ_SPOT_MIN/MAX_USDT,
  LIQ_FUT_MIN_USDT. Premier statut live : spot 70.50 ∈ [15,120], futures 205.95 ≥ 40
  -> RIEN (équilibré — aucun mouvement inutile).

**3. Gouvernance** : ROADMAP mis à jour (virements internes + Earn autorisés à la
boucle bornée ; vente spot libre/marge restent CLI+--confirm uniquement) ; CLAUDE.md
(leviers + architecture). Chaque brique testée ; 423/423 attendu aux portes.

## §76 (addendum) — Notional 25 -> 45 $ : XAUT inclus (décision propriétaire)

Le propriétaire monte FUTURES_AUTO_NOTIONAL_USDT à 45 $ (levier env, effet immédiat) :
XAUT (min ~41.5 $, seul écarté à 25) redevient tradable — vérifié : tout l'univers
faisable à 45. Marges vs murs : 45 ≤ cap/trade 50 ; 3 positions × 45 = 135 ≤ cap 200 ;
risque/trade au SL 1.5 % ≈ 0.68 $. Nota : un choc adverse de −10 % sur un livre plein
(135 $) ≈ 13.5 $ > stop journalier 5 % (~12 $ sur 240) -> le kill-switch ferait son
travail — c'est la protection prévue, pas un trou. Le plancher de marge du gestionnaire
de liquidité suit le sizing : LIQ_FUT_MIN_USDT = 75 (3 × ~22.5 $ de marge à ×2 +
coussin) — vérifié : futures 205.95 ≥ 75, équilibré. Si l'or monte de ~8 %, le minimum
XAUT repassera au-dessus de 45 et le filtre §75 l'écartera de nouveau, visiblement.

## §77 — Optimisation des agents : le prior d'edge cède à l'évidence live, les voix opt-in enfin mesurées

Mesures fraîches (live_ic_audit, 34 990 votes, horizon 60 min) : macro +0.148 ·
sentiment +0.084 · leadlag +0.065 · **simons +0.052 (t +9.8)** · liquidations +0.044 ·
derivs +0.043 · **geometric +0.034 (t +6.3)** · … · flows −0.028. Santé : corr
poids↔IC +0.60 (SAIN) mais DEUX anomalies :

**1. simons et geometric épinglés au plancher 0.2 malgré leur IC.** Diagnostic : pas un
bug, un TIR À LA CORDE entre deux contrôleurs — l'IC-align (§68) tire leur cible vers
~1.0 à chaque learn(), et le prior ADVISORY de l'échelle d'edge (tier NEGATIVE au rejeu
6 ans : geometric −0.07 SUR L'ANNÉE, artefact de régime §54) les re-multiplie par
0.3^0.5 juste après. Équilibre : le plancher. FIX (§77) : le prior CÈDE quand l'IC live
est significativement positif (t ≥ BRAIN_EDGE_PRIOR_IC_T, défaut 3.0 — simons +9.8 et
geometric +6.0 passent, savant +2.1 et divergent −1.3 gardent leur frein). L'échelle
d'edge conserve intacte sa vraie porte : la promotion au trading LIVE. Le juge profond
protège toujours contre les artefacts — mais 35 000 votes réels à +9.8σ SONT l'évidence
courante pour la pondération du CONSENSUS (qui se réadapte en heures si le régime
tourne). Vérifié live : cibles simons 1.06 / geometric 1.02, convergence entamée
(0.20 -> 0.24 en quelques cycles). Débrayage : seuil très grand.

**2. Les voix opt-in (llm/nn/classics) influençaient le consensus SANS être mesurées**
(exclues du journal d'apprentissage §62 -> aucun IC : angle mort « rien d'aveugle »).
FIX : journal SÉPARÉ `.overlay_votes.jsonl` (écrit par _record quand une voix PARLE,
conf > 0 ; jamais lu par learn() ni par l'entraînement du NN -> §62 intact) + bloc
« voix opt-in » dans live_ic_audit (même juge ic_par_agent que les 14). La 17e voix
armée y accumule dès maintenant ; le NN muet n'y écrit rien (par construction : on ne
mesure que ce qui parle). À ≥ 50 votes parlés, l'IC de chaque voix devient un fait.

## §78 — Qualité de pondération : la cible RIDGE corrélation-consciente bat tout (mesuré)

Demande propriétaire : « améliore la qualité de pondération ». Banc d'essai walk-forward
(6 plis, 34 769 échantillons réels, IC de rang du CONSENSUS pondéré vs rendement 1 h) :

  égal            +0.032        cible IC (§68)     +0.038
  poids actuels   +0.076        IC par régime      +0.036
  **ridge Σ⁻¹·IC  +0.123 ± 0.048**  ridge par régime  +0.106

Le RIDGE (régression ridge des rendements sur les 14 votes = poids tenant compte de la
CORRÉLATION entre agents) gagne sur CHACUN des 6 plis, y compris les deux fenêtres
négatives (−0.004 vs −0.135). La leçon : la famille contrarian (sentiment/derivs/
liquidations/carry, pilotée funding+F&G) partage UN pari — l'IC individuel le compte
quatre fois, le ridge une seule, et il concentre sur les porteurs NON redondants
(leadlag 4.7, simons 3.9, structure 3.4 avant bornage). Robustesse : plateau λ large
(0.05–0.5 ≈ +0.12), poids inter-plis de plus en plus stables (corr 0.63 -> 0.99),
0.7 s de calcul. Le régime n'ajoute RIEN par-dessus (buckets qui amincissent les données).

Implémentation : `_ridge_solve` (PUR : négatifs clippés — jamais de flip de signe —,
normalisation moyenne ~1, bornes [0.25, 2.5], mêmes rails que les mults IC) +
`_ridge_mults` (cache 1 h, < 2000 échantillons -> {}) ; la sélection de cible dans
l'alignement devient : ridge si `BRAIN_RIDGE_ALIGN` armé ET disponible, sinon REPLI
AUTOMATIQUE sur les mults IC §68. Le mélange géométrique α, la normalisation, les
clamps [0.2, 3.0], les priors d'edge §77 et le lissage 10 % restent inchangés — le
ridge ne fait que proposer une MEILLEURE cible aux mêmes rails. ARMÉ par le
propriétaire (mandat « qualité de pondération ») ; réversible en une ligne
(BRAIN_RIDGE_ALIGN=0). Cible live constatée : structure/simons/leadlag ~2.9,
famille corrélée ~0.4. La cible se recalcule chaque heure sur un journal qui grandit —
si la structure de corrélation tourne, les poids suivront, mesurés.

## §79 — Réglage des agents sur le rejeu 6 ans : leadlag optimisé, orderflow recâblé, structure disculpé

Le ridge (§78) a promu leadlag/simons/structure en tête des poids — leurs paramètres
méritaient donc l'optimisation MESURÉE (train 2020-2024 / test 2025-2026, IC de rang
à 1 barre 1h, 3 alts vs BTC, stride 4) :

**leadlag : (k=8, w=64) -> (k=4, w=128), ADOPTÉ.** Train : IC +0.054 vs +0.030 ;
TEST hors échantillon : **+0.020 vs +0.003 (7×)**. k=4 domine pour TOUT w (le fade
rapide du mouvement BTC gagne dans tous les régimes). L'agent passe au DOMAINE DU
RÉGLAGE (bougies 1H — transfert exact) au lieu des 90 closes 15m ; env-réglable
(LEADLAG_K/W), fail-safe neutre. L'IC-audit live le re-jugera en continu.

**orderflow : carnet 10 s -> TRADE-SIGN du collecteur, ADOPTÉ.** Le carnet instantané
(IC live −0.014) est un signal de secondes voté pour un horizon d'une heure. Mesure des
features du collecteur 24/7 à 60 min (38 412 obs) : ofi −0.003 · queue −0.009 ·
**trade_sign +0.016 (t +3.2)**. L'agent vote désormais tape×2.5 (gain calibré sur la
distribution : p90 -> vote 0.67, saturation seulement au-delà du p98) quand le
collecteur est FRAIS (summary garde anti-péremption), et REPLIE sur carnet+CVD sinon
(symboles hors BTC/ETH/SOL, buffer mort). Testé (chemin tape + repli).

**structure : AUCUN changement (disculpé par le domaine).** Le rejeu 1h ne voit
aucun edge pour aucune fenêtre (60/120/180 : −0.03..+0.01) alors que l'IC LIVE sur
bougies 15m est +0.031 — le signal BOS/Value-Area vit à la granularité 15 min, le
rejeu 1h y est aveugle. On garde la formulation live, jugée par l'instrument live
(même leçon que §62 : ne pas condamner sur le mauvais étalon).

Balayage d'erreurs (mandat « corriger les erreurs ») : ZÉRO erreur sur 6 h de journaux,
cron liquidité :15 passé (équilibré, plancher 75), journal des voix : 389 votes parlés
déjà accumulés (IC de la 17e voix mesurable sous ~2 jours).

## §80 — Conseils de l'IA Bitget passés au banc d'essai : un adopté, un rejeté, le reste déjà en place

Le propriétaire a partagé les recommandations de l'assistant IA de Bitget (indicateurs
« les plus performants », signaux d'entrée/sortie). Confrontation aux faits du dépôt :

**Déjà implémenté et MESURÉ chez nous** : MA/MACD/Bollinger/RSI (lab §72, familles
CMA-ES, promotion PBO) · structure de prix + volume (agent structure : BOS/CHoCH +
Value Area + anti-piège) · confluence (le consensus pondéré EST la confluence — et sa
pondération vient d'être optimisée §78) · sorties sur perte de momentum (seuil de
sortie consensus), objectif (TP RR 1.5 calibré §68) et invalidation de structure
(invalid_if par agent) · « adapter les indicateurs au régime » : TESTÉ §78 — les poids
par régime NE battent PAS le ridge global (buckets trop minces). Le conseil générique
s'arrête là où la mesure commence.

**Deux idées concrètes restaient non testées — verdict sur 6 ans × 4 symboles :**
  • Cassure CONFIRMÉE PAR LE VOLUME : le filtre (volume barre > 1.3 × moyenne 20)
    améliore le Donchian nu sur 4/4 symboles (Sharpe relatif ~×2 moins mauvais,
    ~30 % de trades en moins). ADOPTÉ au lab : `strat_donchian_vol`
    (donchianvol_20_13, famille CMA-ES n∈[5,80], k∈[1.0,3.0]) — le pipeline du
    dimanche le jugera dans son régime nominal (500 barres, PBO).
  • Entrée sur PULLBACK (retour à l'EMA20 en tendance) : mieux sur BTC, PIRE sur
    SOL/XRP — pas de gain systématique. REJETÉ par la mesure, non shippé.
Nota : sur 6 ans de barres 1h à frais réels, TOUTES les stratégies « toujours en
mouvement » perdent en absolu vs hold — l'intérêt du banc est la comparaison
RELATIVE intra-famille ; le juge absolu reste le lab en fenêtre nominale.

## §81 — Suite Bitget-AI : la bougie de reprise repêche le pullback, le reste trié

Deuxième fournée de conseils de l'assistant Bitget, même traitement (§80 : mesurer,
adopter ou refuser sur chiffres) :

**ADOPTÉ (au lab)** : le pullback avec BOUGIE DE REPRISE (clôture au-delà de l'extrême
de la bougie précédente après repli sur l'EMA20). La version SANS confirmation avait
été rejetée §80 (2/4) ; la confirmation améliore 3/4 symboles sur 6 ans (BTC −4.3 vs
−9.2, ETH −2.1 vs −5.4, SOL +0.48 — POSITIF ; XRP légèrement pire) avec 6× moins de
trades. Entrée au REGISTRE (`pullbackc_20_50`) sans famille CMA-ES (discipline de
multiplicité PBO) — le pipeline du dimanche tranchera.

**DÉJÀ EN PLACE** : stop défini à l'entrée (SL/TP préréglés côté exchange, invariant
Couche 1) · sortie sur perte d'efficacité (seuil de sortie consensus + invalid_if) ·
« risque monté avant l'ordre » (c'est littéralement guards()) · couche de régime
(mesurée §78 : n'ajoute rien aux poids ; regime_gated existe au lab) · filtre volume
sur cassure (§80).

**REFUSÉ, avec motifs** :
  • règles numériques de scalping 1-5 min (stop 0.35 %, TP 0.5/0.8 %) — hors domaine :
    le bot décide au consensus ~1 h, pas à la bougie de 1 min ; nos SL/TP sont
    CALIBRÉS sur nos données (exit_calibration §68, RR 1.5), pas importés ;
  • « martingale / CTA inversé short : très fortes perfs simulées 30 j » — 30 jours
    simulés = artefact de régime type §54 ; la martingale est structurellement
    incompatible avec des caps durs. Non.
  • bot de « grid infinie » (JSON/Python fournis, appels API SIMULÉS à statuts
    aléatoires) — notre grille §72 est BORNÉE, mesurée, se coupe en tendance, et
    l'exécution ne passe que par les exécuteurs audités. « Infini » n'est pas un
    mot qui existe dans un système à murs.
  • « levier moyen 10-20x de votre profil » — PAS le bot (murs ×5, boucle ×2) ;
    probable historique manuel du compte. Aucun changement.

## §82 — Diversification des MÉTHODES : alt-carry (DRY), TP partiels, lab 3×/semaine, exécutions visibles, barre xs

Mandat propriétaire (06/07 soir) : « suis tes recommandations » + lab immédiat +
horaire 3×/semaine + TP partiels + enquête trades absents du dashboard.

**Enquête (résolue)** : les « trades SOL 19:42 / ETH 23:52 » sont les heures LOCALES
(UTC+2) de deux allers-retours RÉELS du bot — SOL short 45 $ 17:28->17:42 UTC, ETH
short 45 $ 21:43->21:52 UTC (+ LAB long 25 $ 13:26, refermé). La fenêtre trades
n'affichait que les positions OUVERTES : un aller-retour de 10 min disparaissait.
FIX : bloc « Exécutions récentes » (8 derniers FUTURES_REAL/TP_PARTIAL/REBASE,
serveur `executions` + rendu) — un trade clos reste visible.

**TP PARTIELS (armés)** : `futures_executor.place_partial_tp` — limite GTC de
RÉDUCTION (jamais d'exposition nouvelle, kill-switch, minima contrat respectés,
échec journalisé jamais bloquant) posée par la boucle après CHAQUE ouverture
réussie : FUTURES_TP_PARTIAL_FRAC (0.5) de la taille à FUTURES_TP1_R (1.0R) ; le
préréglé SL/TP RR 1.5 couvre le reste (« quand c'est possible » = tranche ≥ minima).

**LAB : lancé immédiatement + cadence mar/jeu/sam 05:00** (cron `0 5 * * 2,4,6`).
Premier verdict avec PROMOTIONS : rsi_reversion_14, bollinger_20, evo_bollinger_32,
vp_fade_60, wens_0/3/2.75/0/0 et **evo_grid_49_7** — le régime range favorise la
famille reversion. La grille spot réelle bornée (recommandation n°3) attendra 2-3
confirmations consécutives du lab (le rapport de promotion exige lui-même la
re-validation avant capital) — désormais rapide à 3 runs/semaine.

**ALT-CARRY multi-symboles (recommandation n°1) — construit, DRY par défaut** :
`alt_carry.py`, module de DÉCISION audité (aucun vocabulaire d'écriture ; jambes
DÉLÉGUÉES : spot via spot_trader §67, perp ×1 via futures_executor §45, chacune
avec SES gardes). Scan horaire de l'univers (cron :35) : funding courant, percentile
~90 j (§59), APR annualisé ; OUVRE seulement sur extrême POSITIF (pctl ≥ 90 ET
APR ≥ 12 %), FERME quand ça ne paie plus (pctl < 50 ou APR < 5 %) ; funding négatif
= HORS périmètre v1 (exigerait l'emprunt marge). ANTI-JAMBE-NUE testé : spot
d'abord, échec perp -> compensation immédiate. 10 $/jambe (≤ cap spot/op). Bug
corrigé au passage (percentile_taux attend les lignes brutes). Premier scan réel :
funding de l'univers historiquement BAS (pctl ~1) -> RIEN, correct. **ALT_CARRY_LIVE
reste OFF : observer les décisions DRY journalisées puis armer (décision
propriétaire)** — même rampe que chaque surface.

**Barre de promotion xs (recommandation n°2)** : `xs_paper.promotion_status` —
qualifié si ≥ 30 j, ≥ 20 rebalancements, PnL fictif > 0 (état : 1.3 j · 112 rebal ·
+0.31 $ -> « en cours ») ; learning_health alerte UNE fois à la qualification. La
promotion effective reste une décision propriétaire.

**Moniteur réparé à temps** : la cible RIDGE (§78) diverge de l'IC individuel PAR
CONSTRUCTION -> learning_health jugeait « désaligné » (corr 0.06) précisément parce
que le mécanisme marche. Il juge désormais contre la CIBLE ACTIVE : corr poids ↔
cible ridge = +0.83, SAIN — fausse alarme du cron de minuit évitée.

## §83 — Alt-carry ARMÉ + périmètre REVERSE (emprunt marge autorisé, « bonne gestion »)

Décisions propriétaires (06/07 nuit) : « arme le alt-carry » + « j'autorise les
emprunts marge si bonne gestion et tentative de booster les résultats ».

**Armement** : ALT_CARRY_LIVE=1 (cron :35 exécute désormais réellement) — v1 classic
inchangée (funding positif : spot acheté + perp short ×1).

**v2 REVERSE (le booster)** : funding NÉGATIF extrême (pctl ≤ 10 sur ~90 j) ->
perp LONG + vente du coin EMPRUNTÉ en marge — les shorts paient. La « bonne
gestion » exigée, câblée :
  • le COÛT D'EMPRUNT estimé (ALT_CARRY_BORROW_APR, défaut 15 %/an, réglable) est
    DÉDUIT de l'APR avant toute entrée (net ≥ ALT_CARRY_MIN_APR sinon rien) ;
  • CORRECTION D'UNITÉS dans margin_trader._loan : le notionnel USDT borne les caps,
    la quantité COIN (usdt/prix) part à l'API — sans quoi « 10 » aurait borné 10 USDT
    au garde mais emprunté 10 COINS (~166 $ sur LAB) à l'API ;
  • COLLATÉRAL géré : virement interne spot->marge (surface §67, caps 25/op) AVANT
    l'emprunt, rendu au spot à la fermeture ; échec -> abandon avant toute jambe ;
  • COMPENSATIONS ÉTAGÉES testées : perp raté -> collatéral rendu ; emprunt raté ->
    perp réduit ; vente ratée -> remboursé + perp réduit + rien d'orphelin ;
  • sortie : rachat marge (coussin 2 % ≤ cap), remboursement, perp réduit,
    collatéral rendu ; ferme aussi si le funding repasse ≥ 0 ou net < seuil ;
  • gate dédié ALT_CARRY_NEG (armé) — refermable seul sans couper le classic.
Chaque jambe garde SES gardes §67/§45 (verrous LIVE, kill-switch, caps par op et
par jour, murs futures). État live à l'armement : aucun extrême exploitable
(funding univers à des plus-bas historiques, tous positifs) — la machine attend
proprement des deux côtés désormais. Tests décideur v2 (net d'emprunt, gate NEG,
fermeture sur normalisation) ajoutés.

## §84 — Dashboard : panneau « Méthodes autonomes » + voix opt-in visibles

Mise à jour du dashboard sur la machinerie §76-83 (fichiers locaux uniquement,
zéro appel réseau ajouté) : panneau pleine largeur à 3 colonnes —
  • 🌾 ALT-CARRY : armé (± = reverse autorisé), position en cours (mode/symbole/
    taille), décision et top-3 candidats du dernier cycle journalisé ;
  • 💧 LIQUIDITÉ : floats spot/futures, dernière décision/action du cron :15 ;
  • 🧪 LABO : dernier run, stratégies PROMUES (6 au premier run — affichées),
    cadence mar·jeu·sam, BARRE XS en direct (jours/rebal/PnL vs barre — le paper
    long-short est repassé NÉGATIF (−1.49 $) : la barre juge, c'est son rôle).
Le bloc « Audit IC live » gagne les VOIX OPT-IN (§77) : IC dès ≥ 50 votes, sinon
compte de votes parlés (constaté : classics 2 593, llm 671 — mesure imminente).
Les exécutions TP partiels étaient déjà visibles (§82). Serveur : blocs `methodes`
et `overlay_ic` cachés 60/300 s.

## §85 — Anatomie RÉELLE du réseau au dashboard (l'idée du script matplotlib, version honnête)

Le propriétaire a partagé un script matplotlib « réseau de neurones esthétique »
(halo cumulatif de milliers de lignes à alpha faible, palette thermique) et demandé
s'il pouvait améliorer le bot/dashboard. Verdict : tel quel NON — activations
factices (sin/cos), topologie inventée, image statique : exactement le « faux
graphe » que §69 a éradiqué. MAIS la TECHNIQUE de rendu est bonne et nous avons les
vraies données pour la mériter : `neural_net.anatomy()` expose les matrices de
poids APPRISES du MLP (25→32→32→1 ; ampleur = moyenne |W| de l'ensemble ×5, signe
du membre 0) et le dashboard les dessine en faisceau cumulatif — alpha ∝ |poids|
réel, vert=+/rouge=− (sémantique du dépôt, pas de rainbow), noms des 25 features en
entrée, redessin uniquement au changement de version du modèle (v5 affichée).
Chaque réentraînement de 04:20 changera donc VISIBLEMENT l'anatomie.
Obsidian : rien à câbler — docs/ est du markdown pur, le dépôt s'ouvre tel quel
comme coffre si le propriétaire veut la vue graphe ; le bot, lui, apprend dans ses
journaux mesurés, pas dans de la prose.

## §86 — Carte et anatomie FUSIONNÉES : un seul graphique dynamique, entièrement réel

Demande propriétaire : assembler la carte de connectivité et l'anatomie en un
graphique dynamique. C'est conceptuellement plus juste : le nœud « fusion » de la
carte EST l'anatomie. Un seul canvas (340 px) déroule tout le pipeline RÉEL :
  agents live (activations lissées + particules) -> cerveau -> **MLP DÉPLOYÉ
  25→32→32→1** -> consensus (rejoint par la voie directe du cerveau) -> murs 🔒 ->
  exécution.
Nouveauté qui rend la fusion vivante : `neural_net.anatomy_live()` calcule les
ACTIVATIONS RÉELLES du réseau pour le symbole affiché (vecteur d'entrée x, couches
cachées h1/h2 — passe directe g(x), moyennées sur l'ensemble ×5, p_up) — les
faisceaux de poids appris sont MODULÉS par le signal qui les traverse (alpha ∝
|poids| × |activation source|), les 25 nœuds d'entrée se colorent par leur valeur
live, les cachés par leur intensité, la sortie par P(hausse). Performance : le
faisceau (~1 900 lignes) est PRÉ-RENDU hors écran et recomposé par le RAF — seule
la colonne vertébrale (particules, respiration) s'anime par frame ; re-rendu du
faisceau uniquement quand les données changent. prefers-reduced-motion : statique.
Vérifié : x=25/h1=32/p_up servis par symbole, version du modèle affichée dans le
titre — chaque fine-tuning de 04:20 change l'anatomie ET son flux sous les yeux.

## §86 (addendum) — Fusion REJETÉE par le propriétaire, retour à la carte §74

Verdict propriétaire après visualisation : la fusion « n'apporte rien au graphique ».
Retour à l'ancienne présentation : carte de connectivité ANIMÉE (§74) + panneau
« Anatomie du réseau » SÉPARÉ (§85) — restaurés à l'identique (git checkout du
front pré-fusion). Conservé côté serveur : `neural_net.anatomy_live()` et le champ
`anatomy_acts` (données réelles cachées, coût négligeable, réutilisables — p. ex.
pour enrichir plus tard la ligne d'info ou l'anatomie séparée). Leçon retenue :
deux zooms lisibles valent mieux qu'une grande scène dense.

## §87 — Carte du réseau : l'état de PAROLE de la voix (la seule info nouvelle utile)

Mandat propriétaire : améliorer la carte avec les nouvelles données « uniquement si
pertinent et utile ». Tri honnête : la salience des poids vit déjà dans le panneau
anatomie (la dupliquer = bruit) ; les activations cachées n'aident pas la lecture
agent-niveau. La SEULE info opérationnelle invisible : la carte affichait « ARMÉE ·
P(hausse) 54 % » alors que la porte d'edge rend la voix MUETTE (vote 0 au consensus)
— un propriétaire pouvait la croire contributive. Ajouté : `connectivity_map.gate`
(même logique que nn_agent : mode brut/prudent + edge du mode + muette) ; badge
« ARMÉE · MUETTE (edge −0.014, brut) » vs « PARLE » ; anneau du nœud fusion AMBRE
quand armée-mais-muette (vert = parle, gris = OFF) + suffixe « (muette) ». Rien
d'autre — pertinence avant densité.

## §87 (addendum) — Un SEUL réseau au dashboard

Précision propriétaire : « il y a toujours les deux réseaux » — le panneau
« Anatomie du réseau » (§85) est SUPPRIMÉ aussi (DOM + rendu + bloc serveur, état
~15 Ko plus léger). Il ne reste que la carte de connectivité animée §74, enrichie
du seul ajout jugé utile (§87 : état MUETTE/PARLE de la voix). `neural_net.anatomy()`
et `anatomy_live()` restent disponibles en CLI/API pour inspection ponctuelle.

## §88 — Forensique des trades réels, digest quotidien, tableau des promotions (mandat « 1→5 »)

Mandat propriétaire : exécuter les 5 suggestions dans l'ordre.

**1+4+5 — `trade_forensics.py`** (SAFE, lecture seule) : reconstruit les
ALLERS-RETOURS RÉELS depuis événements exécuteur + fills (les sorties par SL/TP
préréglés et TP1 partiels n'émettent PAS d'événement -> détection pilotée par les
fills), mesure MFE/MAE sur bougies (granularité par ÂGE du trip), R réalisé
(distance au SL préréglé), slippage d'ouverture vs bougie 1 min de la décision,
attribution PnL PAR MÉTHODE (agent). Premiers verdicts sur données réelles :
SOL short +0.19 $ sorti à R+0.64 sur MFE+0.71R (90 % capturé, MAE −0.03R — sortie
consensus EXCELLENTE) ; ETH −0.13 $ (MFE +0.11R/MAE −0.46R) ; slippage médian
+2.4 bps (le limit IOC ne coûte presque rien) ; trade LAB 13:26 = IOC accepté
JAMAIS rempli (0 fill — position jamais ouverte), désormais flaggé « NON REMPLIS ».
DEUX BUGS RÉELS corrigés en chemin : fetch_fills était BTCUSDT-only depuis §47
(PnL bot sous-compté — désormais multi-symboles par ledger, cache par symbole) ;
convention hedge-mode VÉRIFIÉE : le champ side d'un fill = côté de la POSITION
(short s'ouvre ET se ferme en sell), seul tradeSide distingue open/close.

**3 — `promotion_board.py`** : toutes les barres en une vue (voix t=ic·√n ≥ 3,
nn wf_edge > 0, xs 30 j/20 rebal/PnL>0, grille 2 runs lab consécutifs, alt-carry
1 moisson propre) — consommé par le digest + dashboard (colonne Labo). PREMIER
VERDICT MAJEUR : les voix opt-in sont ANTI-PRÉDICTIVES mesurées — classics IC
−0.21 (t = −11 !, n = 2770), llm IC −0.17 (t = −4.5, n = 671). COUPÉES le 07/07
(levier env — le banc 14 + overlays restent) : c'est exactement le travail de
l'instrument §77. Réactivation = nouvelle mesure positive, pas une envie.

**2 — `daily_digest.py`** (cron 07:00, Telegram) : PnL 24 h par méthode +
allers-retours avec R/MFE + slippage + equity/MDD/kill-switch + actions alt-carry
& liquidité + tableau des promotions + santé apprentissage. Le « pourquoi je ne
vois pas X » a désormais une réponse quotidienne automatique.

## §89 — Mandat « 1→6 » : archive, ombre NN, breakeven, watchdog, conviction (rejeté), drill

**1. Archive persistante des round-trips** : l'API des fills n'a que ~40-100 de
profondeur/symbole -> `.trades_archive.jsonl` (append-only, dédup symbol+ts_in),
alimentée à chaque snapshot forensique (digest 07:00 = archivage quotidien garanti).
L'historique de NOS trades s'accumule au lieu de s'évaporer — fondation du Kelly
par méthode.

**2. Ombre de la voix NN** : la leçon classics/llm institutionnalisée — muette par
la porte d'edge, la voix n'accumulait AUCUN IC live (jamais journalisée). Désormais
`nn_shadow` part au journal overlay à chaque cycle (même juge que les 14, zéro
influence sur le consensus). Sa réactivation exigera DEUX preuves : wf_edge > 0 ET
IC live. Vérifié : 22 entrées dès les premières minutes (vote actuel −0.146, short).

**3. Breakeven logiciel (armé, FUTURES_BREAKEVEN=1)** : le hub n'a AUCUN outil
modify-TPSL (place/cancel/get seulement) -> enforcement dans stop_guardian (tick
20 s, organe indépendant) : TP1 encaissé (taille ≤ 60 % de l'ouverture au ledger)
ET prix revenu à l'entrée (±4 bps de frais) -> le RESTE est soldé (réduction pure :
exempte caps, permise même kill-switch). Le SL préréglé d'origine reste le filet
dur. Leçon ETH §88 (+0.11R -> −0.32R) devenue impossible à rejouer en pire.
Décision PURE testée (long/short/pas-de-TP1/prix-au-dessus/position-inconnue).

**4. Watchdog** : carte de fraîcheur §61 étendue à la machinerie §76-88 —
alt_carry (130 min), liquidité (130), digest (tampon .daily_digest_stamp, 26 h),
neural_net_meta (26 h), strategies_out (80 h, gap max sam->mar). Rien d'aveugle.

**5. Filtre de conviction : REJETÉ par la mesure** (39 973 obs, horizon 1 h) :
l'espérance alignée est NÉGATIVE et EMPIRE avec |consensus| — top 10 % : −19 bps
vs −9 global. Le consensus historique (poids majoritairement pré-ridge) est
contrarien à 1 h, cohérent avec le régime range couronné par le lab. Pas de gate
shippé ; mesure rendue RÉPÉTABLE (`live_ic_audit.conviction_par_quantile`) — à
re-juger quand la cible ridge aura une semaine dans les poids. NE PAS inverser
sans validation profonde §54.

**6. Drill de restauration** : `backup_restore_drill.py` — archive->chiffre->
déchiffre->dépaquette->vérifie (liste complète, JSON re-parsés, tailles). PREMIER
DRILL : ✅ 15 registres restaurables, la passphrase de production ouvre bien
l'artefact. Cron mensuel (1ᵉʳ, 08:00) avec alerte Telegram en cas d'échec.

## §90 — Tour complet du bot + premier extrême alt-carry (LAB) : la sécurité a tenu, la moisson a appris

**Tour de santé (07/07 ~01:30 UTC)** : 17 unités systemd actives, 8 crons posés,
0 erreur en 6 h, carte de fraîcheur verte (tampon digest amorcé — premier envoi
07:00), cerveau vivant (poids ridge : leadlag 2.89/simons/structure hauts),
ombre NN accumulée (78 entrées/10 symboles dès la 1ʳᵉ heure), accumulation
réconciliée sans anomalie, dashboard 41 blocs sains, boucle futures flat prête
(long XRPUSDT au consensus +0.45).

**Premier extrême alt-carry — LAB funding −810 % APR (~795 % net)** : détecté ✅,
MAIS la moisson a échoué en 2 temps, chacun instructif :
  1. jambe 10 $ < minimum du contrat LAB (1 LAB ≈ 16.6 $) -> `_taille_jambe`
     ADAPTATIVE (minima × 1.06, bornée par le plus petit cap/op des surfaces
     impliquées ; XAUT correctement infaisable) + décision INFAISABLE visible ;
     caps §67/op alignés sur le mandat §83 : SPOT/MARGIN 20 $/op, MARGIN 100 $/j
     (murs absolus 200/500 INTOUCHÉS) ;
  2. cycle réel relancé : collatéral viré ✓, perp long 17.49 $ OUVERT ✓, EMPRUNT
     LAB REFUSÉ par l'exchange (coin non empruntable en marge croisée — aucun
     endpoint hub ne le prédit) -> COMPENSATION immédiate ✓ (perp refermé, zéro
     jambe nue — la machinerie anti-orphelin a fonctionné SUR ARGENT RÉEL).
     Deux trous corrigés : le collatéral restait en marge sur échec (désormais
     RENDU sur chaque chemin d'échec, + restitution manuelle des 21 $ faite,
     fonds préexistants 41.5 $ du wallet marge non touchés) ; et LISTE NOIRE
     reverse (coin refusé -> cooldown ALT_CARRY_BLOCK_DAYS 7 j, la capacité
     d'emprunt se découvre par l'échec, on ne repaie pas des frais de
     compensation à chaque extrême du même coin). LAB blacklisté jusqu'au 14/07.

## §91 — Plomberie de liquidité autonome (mandat propriétaire)

« Alimente le compte marge pour pouvoir emprunter, transferts/rachats Earn sans
hésiter, fais ce qui est nécessaire au bon fonctionnement — compte test, gère ces
détails seul. » Implémenté :
  • liquidity_manager : branche 1bis PLANCHER DE COLLATÉRAL marge croisée
    (LIQ_MARGIN_MIN_USDT=25, après le plancher futures — les stops d'abord) ;
    action transfer_spot_margin ; rachat Earn si le spot est trop juste ; solde
    marge illisible -> branche sautée (fail-safe) ;
  • alt_carry : collatéral au MANQUANT (`_collateral_manquant` PUR — le float §91
    le rend souvent 0) ; les chemins d'échec ne rendent que ce qui a été AJOUTÉ ;
  • caps §67 FONCTIONNELS calibrés univers entier (jambe XAUT ~46 $) :
    SPOT/MARGIN 50/op·200/j, TRANSFER/EARN 60/op·200/j — murs INTOUCHÉS.
Vérifié live : marge 41.5 $ ≥ plancher -> RIEN (le float existant suffit).

## §92 — DÉLÉGATION TOTALE (décision propriétaire du 07/07/2026)

Verbatim : « Je soussigné propriétaire, t'accorde le droit de prendre des
initiatives de façon autonome, je t'accorde le droit de commande sur tout le
compte Bitget, le retrait est impossible donc pas de tracas pour moi, je souhaite
déléguer totalement la gestion de ce bot à lui-même. »

PÉRIMÈTRE DÉLÉGUÉ (plus besoin de demander) : verrous LIVE et leviers env, caps
effectifs par paliers, armement/coupe des voix SUR MESURE, promotions du lab vers
le réel micro-borné quand leurs barres passent, notional, floats, univers.
Chaque acte : journalisé, notifié Telegram, réversible, motivé par une mesure.

CONSTITUTION (ce que la délégation ne peut PAS toucher — protection du mandant) :
murs absolus en dur, stop journalier −5 % -> kill-switch, 3 portes avant push,
mesure-d'abord (pas d'armement sans chiffre, coupe sur chiffre), retrait
inexistant (clé Trade-only). CLAUDE.md règles 2-3 réécrites en conséquence.

## §93 — DASHBOARD SUR LE TAILNET (régularisation d'écriture, 07/07/2026)

Section écrite APRÈS coup pour régulariser la numérotation : le commit
« Dashboard (§93) : double écoute localhost + IP Tailscale » référençait un §93
jamais versé ici. Décision : le dashboard lecture seule écoute AUSSI sur l'IP
Tailscale de la machine (accès smartphone via le tailnet privé WireGuard) —
JAMAIS 0.0.0.0, l'interface publique reste fermée (dashboard/server.py).

## §94 — MARKET MAKING SPOT BORNÉ, PRINCIPES VIRTU (instruction propriétaire du 07/07/2026)

Le propriétaire demande d'ajouter au bot la technique de market making de Virtu
Financial (synthèse fournie : non-directionnel, capture de spread, contrôle
d'inventaire, verrous multicouches — versée à docs/SAVOIR.md §9 avec ses
implications et ses NON-transpositions retail).

ARCHITECTURE (même patron que liquidité §76 et carry §82-83) :
- `market_maker.py` — module de DÉCISION (aucune écriture directe, audité à part
  par security_agent/scan_mm_decision) : fair = 0.70×microprice + 0.30×mid ;
  spread cible = max(plancher 8 bps, spread carnet, frais aller-retour 2×fee+
  buffer = 23 bps, vol courte ×2.5), plafonné 80 bps ; prix de réservation glissé
  CONTRE l'inventaire (Avellaneda-Stoikov simplifié — écart volontaire vs le
  script fourni : décalage en fraction du DEMI-SPREAD, borné, pas du prix entier,
  qui aurait décalé la réservation de ±40 % au démarrage) ; clamp post-only ;
  tailles asymétriques [0,2] ; côté coupé au-delà de ±0.30 de déviation.
- `spot_trader.py` (surface §67 étendue) : quote() = cotation limit POST-ONLY
  bornée (surface ledger « mm », caps dédiés MM_MAX_PER_QUOTE_USDT 5 $/mur 25 $,
  MM_MAX_DAILY_QUOTED_USDT 400 $/mur 2000 $ — le notionnel COTÉ puis annulé sans
  fill n'a pas le même sens que le notionnel acheté ; anti-boucle-folle) ;
  cancel() = annulation par orderId, possible verrou coupé ET kill actif
  (retirer ses cotations RÉDUIT le risque — fail-safe inverse) ; open_orders()/
  order_info() lecture seule via hub.
- `bitget_market_data.fetch_spot_orderbook` : carnet SPOT public (le merge-depth
  existant est futures).

INVENTAIRE : celui du MODULE SEUL (fills de ses cotations, clientOid « mmq »,
coût moyen pondéré, PnL réalisé/latent) — le stock d'accumulation §44 est
INTOUCHABLE, la vente est bornée à l'inventaire acquis par le MM. Budget de
référence MM_BUDGET_USDT 20 $, inventaire max 15 $.

VERROUS (defense-in-depth) : gate maître MM_AUTO défaut OFF (DRY : plan
journalisé dans .mm_journal.jsonl, rien de placé) ; gardes pré-cotation
fail-closed (carnet illisible/incohérent, spread carnet >120 bps, warm-up <20
mids, premium cross-exchange >0.5 % via fair_price §44 = anti adverse-selection
minimal) ; stop LOCAL journalier du module (PnL réalisé+latent ≤ −1 $ -> cotations
retirées, reprise le lendemain, notifié) ; kill-switch global fail-closed ; puis
TOUTES les gardes de la surface (verrou SPOT_TRADE_LIVE, caps, kill re-vérifié).
La réconciliation/annulation des cotations DÉJÀ ouvertes reste réelle même
désarmé.

HONNÊTETÉ (SAVOIR §9) : un MM retail REST en secondes fournit de la liquidité
stale — l'edge n'est PAS acquis. Mesure-d'abord : boucle */5 min en DRY, mesurer
dans .mm_journal.jsonl le spread capturable et (après armement éventuel micro)
le PnL par fill AVANT toute montée. Armement = décision mesurée (délégation §92),
jamais par défaut. Tests : moteur pur, gardes, fills/coût moyen, surface quote/
cancel (tests_audit). TTL des cotations = 1 cycle (annule-et-recote).

CRON À INSTALLER PAR LE PROPRIÉTAIRE (l'environnement de la session a refusé
l'écriture du crontab — persistance non explicitement demandée) ; décommenter
en même temps l'entrée .mm_journal.jsonl de la CARTE_FRAICHEUR du watchdog :
    */5 * * * * cd ~/bitget_termux_repo && /usr/bin/python3 market_maker.py --cycle >> ~/market_maker.log 2>&1

MESURE DU BANC (07/07/2026, mm_lab.py — BTCUSDT, 30 j de 5 m, 8 597 barres,
grille frais/vol, verdict = PnL>0 ET folds+ ≥60 % ET ≥30 fills) :
  - frais 10 bps · vol ×2.5 (prod)  : −11.64 $ (−0.39 $/j), 2 189 fills, folds+ 0 %
  - frais 10 bps · vol ×1.5 (serré) : −17.28 $ · vol ×3.5 (large) : −6.63 $
  - frais 8 bps (réduits)           : −10.11 $
  - frais 0 (théorique)             : −0.85 $ — MÊME SANS FRAIS le PnL est négatif
ÉCHEC sur TOUTE la grille, et le banc est une BORNE SUPÉRIEURE (fills sans file
d'attente). Lecture : l'ADVERSE SELECTION domine le spread capturé — on est
rempli quand le prix traverse (et continue), l'inventaire se déprécie plus vite
que les 23 bps encaissés. Confirme mot pour mot le caveat du SAVOIR §9 (« un
retail lent fournit de la liquidité stale »).

DÉCISION (mesure-d'abord §45) : MM_AUTO reste OFF — pas d'armement. Le module
reste en DRY (cron */5) : le journal live mesurera le spread capturable RÉEL
(microprice + carnet, ce que le banc n'a pas) ; ré-évaluation seulement si le
DRY contredit le banc, ou avec des frais maker ≈ 0 (promo/VIP). Le banc mm_lab
est rejouable : python mm_lab.py SYMBOL JOURS.

ADDENDUM MULTI-PAIRES (07/07/2026, après-midi) : le module cote désormais
plusieurs paires (MM_SYMBOLS CSV — état/inventaire PAR paire, specs de
l'exchange par paire, budget/inventaire max PARTAGÉS divisés par le nombre de
paires, stop journalier GLOBAL), et le banc a un mode univers
(python mm_lab.py --univers 30) : spread carnet L1 RÉEL mesuré par paire,
frais maker MESURÉS sur nos fills (10 bps, 8 bps déduction BGB active — le
makerFeeRate public à 20 bps est un plafond théorique, pas le taux du compte).
MESURE sur les 10 paires de l'univers (30 j de 5 m, frais 8 bps) : ÉCHEC
PARTOUT, folds+ 0 % sur chaque paire — du moins pire au pire :
LABUSDT −0.17 $/j · XAUT −0.22 · BGB −0.29 · SOL −0.30 · ETH −0.33 ·
BTC −0.34 · XRP −0.35 · LIT −0.35 · DOGE −0.38 · HYPE −0.39. Les spreads
carnet plus larges (LIT 3.8 bps, LAB 1.8 bps) ne compensent PAS : l'adverse
selection croît avec le spread/la vol au même rythme que le spread encaissé.
La diversification (principe Virtu n°4) diversifie les POCHES, pas le signe
de l'espérance. DÉCISION inchangée et RENFORCÉE : MM_AUTO reste OFF sur tout
l'univers ; le DRY multi-paires reste le seul juge encore ouvert.

## §95 — DASHBOARD : PORTEFEUILLE TOTAL, RÉFLEXION VIVANTE, CHAT LLM, EXPLORATEUR API (instruction propriétaire du 07/07/2026)

Instruction : « ajouter le montant total du portefeuille · un cadre pour
visualiser la réflexion en cours · un cadre chat bot (toi ou un autre LLM) ·
une visualisation de tout ce que fournit Bitget via l'API ». Quatre ajouts,
TOUS en lecture seule (le dashboard ne peut toujours RIEN exécuter) :
1. **Portefeuille total** : `real_positions.all_account_balance()` (endpoint
   officiel all-account-balance, 1 GET signé de consultation, parse PUR testé)
   -> bandeau « RÉEL PORTEFEUILLE » + chips de ventilation par compte
   (spot/futures/earn/bots/marge/funding) dans la carte positions. ~1 145 $
   au 07/07 (earn 686 + futures 208 + spot 113 + bots 95 + marge 44).
2. **Réflexion en cours** : carte narrative rendue CÔTÉ CLIENT depuis l'état
   déjà servi (zéro producteur en plus) — cerveau (biais/consensus/conviction
   ajustée/accord/groupthink + voix décisives avec leurs notes), boucle
   directionnelle (décision préview + RAISON + throttle + positions), gardes
   (kill-switch, stop journalier avec marge restante, murs), méthodes.
3. **Chat** : POST `/api/chat` -> `dash_chat.py` (SAFE, fail-safe) avec
   contexte COMPACT `chat_context()` (pur, testé, ~4.5k chars — les journaux
   bruts des méthodes en sont exclus, mesurés à 3.3k chars pour rien).
   Backends : OpenRouter cloud par DÉFAUT (anthropic/claude-haiku-4.5, 1.4-3 s
   MESURÉ, budget journalier PARTAGÉ avec la 15ᵉ voix : 0.50 $/j + ledger) ;
   Ollama local qwen2.5:7b en OPTION (gratuit mais MESURÉ impraticable sur
   gros contexte : prompt-eval < 4 tok/s quand le modèle est éjecté vers le
   swap par les boucles — timeout à 2 min sur ~1 850 tokens). L'historique
   client est BORNÉ (8 messages) et FILTRÉ (un rôle system injecté côté
   navigateur est ignoré). Le LLM ne peut RIEN exécuter : il reçoit un dict,
   rend du texte.
4. **Explorateur API Bitget** : GET `/api/bitget` -> `bitget_explorer.py`
   (SAFE) — 15 sections WHITELISTÉES (compte : soldes, avoirs spot/earn,
   compte+positions futures, marge iso/croisée, ordres spot ouverts,
   fills/bills futures via futures_report ; marché : tickers spot/futures,
   funding, open interest, annonces scorées), requête À LA DEMANDE (cache
   30 s), rendu tableau générique (epoch ms/s -> UTC, échappement HTML).
   AUCUN chemin d'ordre dans le module (fills/bills passent par les lecteurs
   déjà audités) ; sections virements/retraits volontairement ABSENTES.
Sécurité : `bitget_explorer.py`, `dash_chat.py`, `real_positions.py` ajoutés
au périmètre de scan de security_agent (scan générique : zéro mot d'ordre).
4 tests ajoutés (parse ventilation, whitelist+curation explorateur, messages
chat bornés/filtrés, contexte compact sans blob). Leviers .env :
DASH_CHAT_MODEL_LOCAL/CLOUD, DASH_CHAT_MAX_TOKENS, DASH_CHAT_TIMEOUT_S.

## §96 — RADAR DE CONSENSUS : REDESIGN EN INSTRUMENT (instruction propriétaire du 07/07/2026)

Instruction : « fais de la carte de consensus un vrai outil dynamique, utile,
visuellement parlant — sinon je ne vois pas l'utilité de l'afficher ». L'étoile
radiale animée (satellites orbitaux) était de la décoration : elle ne montrait
ni l'histoire, ni la distance au seuil, ni ce que la boucle allait FAIRE.
Remplacée par un RADAR tabulaire par symbole, aligné sur la réalité de la
boucle §47 :
- serveur : `radar_univers()` (PUR, testé) construit depuis brain_log, par
  symbole : dernier consensus avec la MÊME règle de fraîcheur que
  `consensus_frais` (périmé > 15 min -> la boucle l'ignore -> affiché estompé
  + ⚠), série 6 h downsamplée (48 pts), voix d'agents pour/contre (bande
  morte ±0.1 — un vote à ~0 n'est pas une opinion), âge de lecture ;
  + faisabilité §75 par symbole (`_taille_faisable`, spec en cache) ;
- front : une LIGNE par symbole — barre centrée avec graduations au seuil
  ±0.35, valeur, ● ambre = actionnable, ⛔ = infaisable (écarté à la
  décision), sparkline 6 h avec lignes de seuil + momentum Δ1 h (↗/↘),
  badge de POSITION tenue (sens + notional), fraîcheur colorée ; en tête :
  jauge du net marché + compteurs ↑/↓/actionnables + la DÉCISION préview de
  la boucle avec sa RAISON (le « et donc ? » du panneau) ; clic sur une
  ligne = charge l'actif sur le graphique. Canvas/étoile supprimés (ainsi
  que la légende à couches et ~60 lignes d'animation orbitale).
Ce qui était invisible avant et se lit maintenant en 2 s : à quelle distance
du seuil est chaque symbole, dans quel SENS ça évolue depuis 6 h, combien
d'agents portent le signal, si la lecture est fraîche, si le candidat est
tradable, et ce que la boucle va faire de tout ça.


## §97 — AUDIT FORENSIQUE : ANGLE MORT DE MESURE + DÉ-RISQUE FUTURES (07/07/2026)

Parti d'une question propriétaire (« amplifier l'agent geometric aiderait-il ? »),
un audit en éventail (4 agents lecture seule) a démonté une hypothèse fausse et
révélé un angle mort SYSTÉMIQUE de la pondération. Rien touché aux murs.

**geometric — poids bas CORRECT, pas un frein bloqué.** À l'horizon de jugement
du cerveau (1 h), son IC live est NÉGATIF (rank −0.012, t −2.5). Le « +6.3 » du §77
était un snapshot ~24 h PÉRIMÉ. Son edge 24 h (+0.033) est un MIRAGE de régime :
tout `brain_log_history` ne fait que **4,28 jours**, soit ~4 fenêtres 24 h non
chevauchantes/symbole ; net de frais ~12 bps brut vs 23 bps de coût plancher
(SAVOIR §, breakeven) ; aucune porte profonde ne teste 24 h (DSR calé à 8 h, zone
la plus négative). Verdict : ne rien brancher, juste MESURER l'IC 24 h dans le temps.

**L'angle mort à trois couches (le vrai sujet).**
1. *Échantillon 4 j / un seul régime* : les « n=46k » de `live_ic_audit` sont ~4 j
   de rendements forward très recouvrants -> t-stats gonflés (geometric a basculé
   +6.3 -> −2.5 au même horizon en 4 j). Plafonne la confiance sur TOUT l'IC live.
2. *Mismatch Pearson vs Rank IC* : la cible RIDGE (§78, `_ridge_solve`) qui fixe 85 %
   du poids (α=0.85) optimise un **Pearson pondéré-magnitude** (≈ PnL, sizing par
   |vote|), mais `live_ic_audit`/dashboard affichaient un **Rank IC**. Signe OPPOSÉ
   pour liquidations/derivs/technicals (± carry/geometric). D'où l'illusion « le ridge
   réhabilite ce que l'IC plante » : c'est le MÊME agent vu dans deux métriques.
   Le ridge est SOLIDE (cond ~25, bootstrap stable, 45k paires) — le défaut était
   d'OBSERVABILITÉ, pas de calcul. (technicals : rank −0.03 mais pearson +0.04 stable ;
   derivs/liquidations : rank +0.04 mais pearson −0.13 ET corrélés 0.993 -> plancher
   ridge justifié, pas de l'edge jeté.)
3. *Juge de santé circulaire (§82)* : `learning_health` comparait les poids à la cible
   ridge ELLE-MÊME (corr +0.78 « SAIN » garanti) -> aveugle à un sur-poids perdant.

**Correctif de l'instrument (ce commit).**
- `agent_validation.pearson_ic()` (pur) + `evaluate()` expose `pic`/`pic_t` à côté du
  rank IC.
- `live_ic_audit` affiche les DEUX IC + marqueur `⚠ SIGNES OPPOSÉS` (fin de l'angle
  mort d'observabilité).
- `learning_health` : garde NON-CIRCULAIRE `overweight_negatifs(weights, pic)` —
  alarme si un agent SUR-pondéré (poids > 1) est significativement NÉGATIF en PEARSON
  (t ≤ −2). En Pearson, AUCUN sur-poids actuel ne s'allume -> l'alarme « 4 agents
  live-négatifs » de l'audit était elle-même un artefact du Rank IC. `healthy` exige
  désormais les DEUX gardes (corr-cible ET pearson). 3 tests dédiés (447/447).

**Chemins d'argent (mesure forensique, 168 h).** Seuls nets-positifs PROPRES :
accumulation spot (+5,55 % latent) et funding carry (+0,26 $), sans levier. Futures
directionnel +1,7 $ mais **82 % vient d'UN trade LAB** ; le cœur BTC saigne les frais
(7 round-trips, −0,058 $, 0 gagnant). Porte d'edge outrepassée, 0 agent LIVE.
liquidity_manager + 4 surfaces §67 : armées LIVE mais INERTES (0 action). MM OFF (banc
négatif) = correct.

**Acte autonome journalisé (§92) : `FUTURES_AUTO_NOTIONAL_USDT` 45 -> 25.** Dé-risque
motivé par la mesure (edge non prouvé, porté par un seul trade). Réversible d'un flag.
Murs 50/250 inchangés. XAUT (min ~41,5 $) redevient infaisable — non prouvé porteur
d'edge. `FUTURES_EDGE_GATE_OVERRIDE` (fermeture = arrêt total de la boucle
directionnelle) laissé à l'arbitrage propriétaire.

**Faux positif écarté :** `strategy_lab` tourne bien (fichiers `strategies_out/`
datés 07/07 05:00) ; `knowledge.json` figé au 27/06 relève de `knowledge_base.py`
(sous-système SAVOIR), pas du lab.


## §98 — CODE « ÉCRIT MAIS JAMAIS LU » : mesurer avant de brancher (07/07/2026)

Suite au §97 (question propriétaire : « comment est-ce possible que ça n'ait jamais été
lu ? assure-toi que tout soit lu »). Deux machineries écrivaient/existaient sans que leur
moitié LECTURE ne soit branchée. Diagnostic AVANT de câbler quoi que ce soit.

**`situation_memory` (mémoire de situations, réflexion post-trade idée #6).** `record()`
câblé dans `learn()` (écrit ~18k lignes `.situation_memory.jsonl`), mais `recall()`/
`expectancy_hint()` JAMAIS appelés (ajoutés au même commit 8c6c5cf, moitié lecture jamais
connectée — capacité construite, intégration oubliée ; docstring « ADVISORY hors chemin
critique »). AVANT de la brancher dans la décision, on la MESURE (c'est ça, « la lire »),
walk-forward sur les 18k lignes : **hit-rate 0.516 < base 0.536, IC hint→résultat −0.01
(t −1.28) sur 16k** -> AUCUN pouvoir prédictif, la brancher AGGRAVERAIT le consensus.
Piège rencontré en implémentant le monitor : le `hit-rate vs base` FLIPPE de signe selon
la fenêtre (−0.35 / −0.02 / +0.09) parce qu'il est confondu par le régime (marché qui
tend -> base_rate haute -> suivre la tendance « gagne » gratis). VERDICT basé sur l'IC
RÉGIME-NEUTRE (corrélation, retire le biais constant) : stable à ~0, t < 1.
- `situation_memory.evaluate()` (le « read » manquant, PUR, `_pearson` inline sans dépendance,
  fenêtre bornée coût stable) branché dans `revue_hebdo` -> désormais LU et surveillé chaque
  dimanche ; recommandation d'armement seulement si IC > 0 ET t ≥ 2 sur PLUSIEURS semaines
  (jamais sur une). Décision : garder l'écriture (accumulation), la lecture reste ADVISORY
  et NON branchée dans la décision tant que la mesure ne le justifie pas. 1 test.

**`data_guards` (quote_valid / quote_fresh / cap_by_liquidity).** `series_ok` câblé ;
les 3 autres jamais appelées — mais ce n'est PAS un simple oubli : (a) `quote_valid` est
déjà appliqué INLINE dans `market_maker.build_snapshot` (`bid<=0 or ask<=bid`), version
plus stricte -> unifié pour utiliser la garde partagée testée (source unique, zéro
changement de comportement, `ask<=bid` préservé) ; (b) `cap_by_liquidity` est une garde
de TAKER (plafonner un IOC par le top-of-book) dont la place est le chemin exécuteur
(module d'ordre autorisé, money-critique) ; (c) `quote_fresh` exige un âge de cotation non
plombé aujourd'hui. Leçon : « tout lire » ≠ tout brancher — deux de ces gardes changent
un comportement d'exécution et relèvent de la décision (mesure/plomberie), pas de l'oubli.

**`cap_by_liquidity` câblé dans l'exécuteur (§98, décision propriétaire 07/07).**
`futures_executor.liquidity_capped_notional()` (PUR) plafonne le notionnel d'OUVERTURE
par la liquidité affichée au top-of-book du côté TRAVERSÉ (long -> ask, short -> bid) via
`data_guards.cap_by_liquidity`. Appliqué dans `execute()` AVANT `guards()` (les caps durs
voient le notionnel réduit), **openings seulement** (`reduce=False` — une fermeture doit
rester entière), **ne peut QUE réduire**, **fail-open** (pas de carnet -> inchangé). Le
carnet vient de `fe._top_of_book(sym)` (MÊME ticker que `_mark_price`, aucune requête en
plus, gardé par `hub.available()`), FOURNI par `futures_auto` -> `execute()` ne déclenche
aucune requête réseau (tests hermétiques). Valeur : les thin alts de l'univers (LAB/HYPE/
BGB) où un IOC de 25 $ pourrait balayer plusieurs niveaux. Trace `liquidity_capped_from`
au journal quand le cap mord. 1 test dédié (450/450).

**`quote_fresh` câblé (§98, horodatage ajouté).** `_top_of_book` calcule `age_ms` depuis
le champ `ts` (horodatage marché, ms) de la ligne ticker (age réel mesuré ~254 ms sur BTC).
`futures_executor.quote_too_stale(top, max_age_ms)` (PUR, via `data_guards.quote_fresh`) :
True SEULEMENT si l'âge est LISIBLE et > seuil (`FUTURES_MAX_QUOTE_AGE_MS`, défaut 3000 —
généreux, ne mord qu'un flux GELÉ) ; âge absent -> False (fail-open, on ne bloque pas sur
une donnée manquante) ; petit âge négatif (dérive d'horloge) clampé -> frais. `futures_auto`
ABSTIENT l'ouverture sur staleness avérée (entry/SL/depth d'un flux gelé non fiables) ;
un seul fetch du carnet réutilisé pour le cap ET la fraîcheur. Les 3 gardes `data_guards`
utiles à l'exécution futures sont désormais toutes câblées (series_ok au cerveau, quote_valid
au MM, quote_fresh + cap_by_liquidity à l'exécuteur). 1 test dédié (451/451).


## §99 — DASHBOARD : détail complet des positions futures RÉELLES (07/07/2026)

Demande propriétaire : enrichir le panneau « Trades RÉELS en cours » (profit total, P&L
réalisé, ROI, marge, P&L latent, entrée/mark, liquidation, SL, TP partiel, TP final,
frais). Deux sources, chacune AUDITÉE et lecture seule :
- **`real_positions.futures()` enrichi** depuis le MÊME appel position Bitget déjà utilisé
  (`/api/v2/mix/position/all-position`, endpoint /position/, hors namespace d'ordre) :
  `achievedProfits` (P&L réalisé), `totalFee` (frais), `liquidationPrice`, `breakEvenPrice`,
  + calculés `total_pnl_usdt` (réalisé+latent), `roi_pct` (latent/marge).
- **SL / TP final / TP partiel** : PAS via l'API d'ordre (le dépôt interdit `/api/v2/mix/order`
  dans le code de lecture — `security_agent` le flague en WARNING, principe « zéro chemin
  d'ordre » de `bitget_explorer`). Source = le LEDGER de l'exécuteur (`futures_real_ledger.json`,
  audité) : les valeurs que le BOT a lui-même posées (`presetStopLossPrice`/`presetStopSurplusPrice`
  à l'ouverture §45, event `FUTURES_TP_PARTIAL` §82). `real_positions._parse_ledger_sltp()`
  (PUR) prend la dernière ouverture + le dernier TP partiel réussi par symbole ; `futures_sltp()`
  lit le ledger. Rattaché aux positions dans `snapshot()`. Best-effort : valeur absente -> « — »
  (jamais une valeur douteuse sur le risque réel).
- Front : chaque position garde sa ligne résumé + une sous-ligne `.rt-d` de détail. 2 tests
  (parse position enrichie + parse ledger SL/TP). 452/452.
Note : première tentative via `/api/v2/mix/order/orders-plan-pending` REJETÉE par
`security_agent` (WARNING) — d'où le pivot vers le ledger, plus propre ET plus fidèle (ce
que le bot a réellement posé). `bgc` n'expose pas de lecteur d'ordres plan futures.

## §100 — 18ᵉ VOIX QUANTIQUE : circuit variationnel opt-in, inférence numpy pure (08/07/2026)

Demande propriétaire : « branche la 18ᵉ voix quantique ». Prolonge le prototype QML
(`qml_prototype/`, 6 qubits PennyLane/PyTorch) en une VOIX du cerveau, strictement sur le
patron des 15ᵉ/16ᵉ/17ᵉ (opt-in, additive, fail-safe, bornée, banc 14 gelé intact §62,
murs `guards()` intouchés).

**Architecture (contrainte ERR-004 : PennyLane INTERDIT dans le Python système)** :
- **Entraînement au labo** (`qml_prototype/train_voice.py`, venv isolé) : circuit 6 qubits ×
  4 couches (AmplitudeEmbedding L2 + StronglyEntanglingLayers), MÊMES features que la 16ᵉ
  voix (`neural_net._dataset` : 14 votes du banc + contextuelles causales, étiquettes §71/§73),
  MÊME validation (walk-forward 6 plis temporels, purge anti-fuite, edge = acc − base,
  borne prudente − se). Poids exportés en JSON (`qml_voice_weights.json`, 4×6×3, committable).
- **Inférence LIVE en numpy PUR** (`qml_quantum_sim.py`, SAFE) : simulation EXACTE du
  vecteur d'état 64 amplitudes — Rot/CNOT/embedding aux conventions PennyLane, PARITÉ
  vérifiée à 5e-16 (`train_voice.py --parity`). AUCUNE dépendance nouvelle, inférence ~µs.
- **`qml_agent.py` (18ᵉ voix, SAFE)** : gated `QML_AGENT_ENABLED` (défaut OFF), porte
  d'edge `QML_EDGE_GATE` prudent/brut (§71), confiance plafonnée `QML_AGENT_CONF_CAP` 0.5,
  cache TTL, `feature_hash` refusant un modèle désaligné, ombre `qml_shadow` journalisée
  quand la porte la tait (§89 — IC live jugé par le même audit que les 14), alerte Telegram
  à chaque transition de porte au réentraînement. Câblée dans `swarm_brain._collect_votes`
  après la 17ᵉ voix (votes en context, pas de recalcul).

**Première mesure (6000 exemples récents, cap journalisé `QML_TRAIN_MAX_N`)** :
wf_edge −0.0519 (se 0.0399), borne prudente −0.0918, acc 0.522 vs base 0.574 → **la porte
TAIT la voix** (comme NN v4 §73/§88). La voix est branchée et ARMABLE sans risque : elle ne
parlera que si un réentraînement démontre un edge positif (alerte Telegram automatique) ;
en attendant, `qml_shadow` accumule l'IC live. Verdict honnête : à 6 qubits/72 paramètres,
la fusion quantique ne bat pas (encore) le taux de base — c'est un INSTRUMENT DE MESURE de
plus, pas une promesse. Tests : 4 ajoutés (neutralité OFF, porte configurable + muette,
exactitude/invariances du simulateur, refus des poids désalignés).

## §101 — COLLECTEUR DE DONNÉES : agent scraper + agent trieur thématique (08/07/2026)

Demande propriétaire : « un collecteur de données avec un agent scraper (scrapling) et
un agent trieur qui classe les résultats en catégories qu'il crée selon les thèmes ».
Pipeline SAFE en deux agents découplés par fichiers (`data_collector/`) :
- **Scraper** (`scraper_agent.py`) : scrapling 0.4 (`[fetchers]`, curl_cffi) dans le venv
  ISOLÉ `data_collector/.venv` — ERR-004 : dépendance tierce jamais dans le Python
  système. Sources `sources.json` (5 flux RSS crypto publics), GET poli (pause 1,5 s,
  timeout 25 s, ≤ 20 éléments/source), RSS parsé en stdlib (les parseurs HTML mutilent
  `<link>`), dédup par sha1(url|titre), sortie `raw_items.jsonl`. Fail-safe par source
  (mesuré : theblock 403 -> ignoré proprement, 4/5 sources OK).
- **Trieur** (`sorter_agent.py`) : Python système PUR (zéro dépendance). Mots-clés
  pondérés (titre ×3, stopwords FR/EN, accents pliés) ; cosinus ≥ 0.18 avec une
  catégorie existante -> l'élément la REJOINT et enrichit son profil (Counter borné à
  40 termes) ; sinon CRÉATION d'une catégorie nommée des 3 mots-clés dominants.
  DÉTERMINISTE (pas de LLM, pas d'aléa) ; état incrémental (`sorter_state.json`).
Première exécution réelle : 70 éléments -> 38 catégories créées, agrégation correcte
des gros thèmes (bitcoin-bulls-battle ×14, crypto-sec-propose ×8) ; les singletons se
consolident au fil des collectes (le profil des catégories s'enrichit). Artefacts
locaux gitignorés. Test déterministe du trieur dans `tests_audit`. Cron éventuel de
collecte périodique = acte propriétaire (couche de permissions).

## §102 — RE-MESURE WALK-FORWARD DU RIDGE : λ 0.2 → 2.0, l'artefact carry éliminé (08/07/2026)

Déclencheur : l'alerte §96 (learning_health) — carry sur-pondéré (poids 3.0) avec un
pearson marginal NÉGATIF (−0.042, t −9.9). Diagnostic du /lance-correction : les poids
suivent la cible ridge ; c'est le ridge qui donnait à carry le mult MAX (2.5).

Protocole (scratchpad/wf_ridge_remeasure.py, lecture seule) : réplique du §78 sur le
journal ACTUEL (56 977 entrées, ~5.3 j) — 6 plis temporels, purge H+600 s, cible réapprise
à chaque pli via `_ridge_solve` (code de production), IC consensus pearson + rang, aux
3 horizons instrumentés 900/3600/14400 s (D1/W1 infaisables sur 5 j de journal —
tf-ladder-ok). Comparaison biaisée EN FAVEUR des poids courants (dérivés de la cible
calculée sur tout le journal, test inclus).

Résultats (horizon de production 3600 s) :
- La PROCÉDURE ridge vaut toujours : wf pearson +0.034 vs +0.021 (poids courants)
  vs −0.051 (poids égaux), ridge>courants 3/5 plis. Le chiffre-titre du §78
  (+0.123 vs +0.076, 6/6) ne tient plus : l'IC consensus décroît nettement sur les
  2 plis récents (régime) — l'edge du banc s'est affaissé cette semaine.
- **carry = artefact** : coefficient au PLANCHER (0.25) sur 15/15 réajustements
  hors-échantillon (5 plis × 3 horizons) ; le 2.5 du fit plein-journal vient
  ENTIÈREMENT du dernier bloc (~1 j) en-échantillon. Le fit plein-journal SANS le
  dernier bloc (80 % des données) donne déjà 0.25.
- Balayage λ (appariés par pli) : 0.2 → wf +0.0348 ; plateau 1.5–3.0 → +0.040/+0.041,
  gains concentrés sur les plis récents (~0 vs négatifs à 0.2) ; et dès λ≥1 le fit
  plein-journal cesse de contredire le walk-forward (carry_full 2.5 → 0.25 à λ=2).

Décision (§92, palier motivé/réversible) : `BRAIN_RIDGE_LAMBDA=2.0` posé dans `.env`
(milieu du plateau ; défaut code inchangé à 0.2). Nouvelle cible plein-journal à λ=2 :
carry 2.5→0.25, savant 2.5→1.11, technicals 0.81→2.5, simons 2.18→1.73, leadlag 2.5 —
réalignée sur le classement pearson marginal §96 (technicals +0.058 t 13.9 en tête).
Les DEUX instruments (garde §96 et cible ridge) convergent désormais ; l'alerte carry
devrait s'éteindre d'elle-même au prochain rafraîchissement (cache 1 h, mélange α=0.85 :
poids carry 3.0 → ~0.4). Réversion : supprimer la ligne du `.env`.

À re-mesurer (~15/07, journal ≥ 2 semaines) : le plateau λ tient-il hors de cette
fenêtre ; l'affaissement d'edge des plis récents est-il un régime passager ou une
dérive ; carry rouvre-t-il hors-échantillon.

## §103 — TROIS LABOS QUANT : régime, GARCH fitté, geometric v2 (08/07/2026)

Suite au balayage PyPI (§92) et à l'installation de ruptures/hmmlearn/arch/POT/dcor/nolds
(protocole ERR-004, pivots numpy/scipy/sklearn/torch inchangés), trois laboratoires
hors-ligne (scratchpad/{regime,garch,geometric_v2}_lab, lecture seule, walk-forward purgé).
Les sous-agents ont été coupés sur la limite de session ; les mesures avaient abouti
(resultats.json), verdicts rejoués/agrégés dans la boucle principale.

**1. Détecteur de régime (ruptures + hmmlearn)** — motivé par l'affaissement d'edge §102.
Flags STRICTEMENT causaux (HMM filtré forward pas-à-pas, pas de Viterbi qui regarde en avant ;
ruptures Pelt), échelle 5m→1W sur BTC+ETH, 3 mesures (le sous-agent a été coupé sur la limite
de session puis a repris — verdict complet ci-dessous, plus riche que la 1ʳᵉ extraction) :
- (a) Pertinence-vol (le flag prédit-il |rendement| forward ?) : FORTE — ic_phaut_absfwd
  t médian +6.33, significatif 7/8 séries ; bat même la vol EWMA (net à 1H : +0.176 vs +0.118),
  cohérent BTC↔ETH (phi +0.62 à 1H). S'affaiblit en 1D/1W (échantillon mince).
- (b) Séparation directionnelle sur un momentum NU : NULLE — |t_delta| max 3.11, 1/26
  (série×flag) au-dessus de 3, deltas négatifs ; et le momentum n'a de toute façon aucun edge
  propre dans l'un ou l'autre régime.
- (c) MODULATION DU CONSENSUS LIVE (le twist) : sur brain_log_history 1H, le flag HMM (ajusté
  sur l'historique strictement antérieur puis filtré forward) CONCENTRE la conviction du banc —
  IC de rang BTC +0.058→+0.178 (régime haut, delta +0.120), ETH +0.115→+0.28 (delta +0.156).
  L'edge du banc DOUBLE en haute-vol. MAIS : journal de 5,3 j, UN SEUL bloc coïncidant avec le
  régime que §102 pointe (18 bascules de flag) — CONTRÔLE DE COHÉRENCE, PAS UNE PREUVE.
Verdict : instrument de VOLATILITÉ (vol-targeting / sizing / contexte de risque), PAS une porte
d'edge directionnelle sur signal nu. Le seul fil prometteur = (c), la modulation du consensus
par le régime — à RE-MESURER en walk-forward multi-plis vers ~15/07 quand le journal aura
≥2 semaines, AVANT toute idée de branchement. Sweet-spot 1H/4H.

**2. GARCH fitté vs figé (arch)** — arch GARCH(1,1) MLE fitté par fenêtre (refit /40 pas,
filtrage forward entre) contre volatility.garch11_vol figé (α=0.10/β=0.85), EWMA(0.94) et
écart-type naïf. Prévision de variance 1 pas, QLIKE (principale) + MSE, 5 plis, t apparié.
Résultat sans ambiguïté : QLIKE médian figé 1.8535 < arch 1.8916 < ewma 1.9164 < naïf 1.9981.
Le figé bat arch sur 11/12 séries ; arch est SIGNIFICATIVEMENT PIRE (t≥3) sur BTC 1H et 1D ;
vol-targeting à égalité (6/12). Le fit par fenêtre surapprend le bruit local ; les paramètres
robustes façon RiskMetrics généralisent mieux hors-échantillon. **Décision : volatility.py
INCHANGÉ ; arch reste un outil de labo (pas de dépendance ajoutée en prod).**

**3. Features geometric v2 (POT / dcor / nolds)** — 14 features candidates (W1-gauss/POT,
W1-dérive de régime et de forme, dcor BTC↔ETH et dcor_excess non-linéaire pur, λ₂ du graphe
re-pondéré dcor vs Pearson vs RMT de l'agent, DFA/Hurst/SampEn/corr_dim), contre le baseline
geom_vote rejoué. Le sous-agent a REPRIS après la coupure et bouclé l'ÉCHELLE COMPLÈTE
1m→1W × 2-4 symboles (ERR-001 satisfaite), walk-forward 6 plis purgés, horizons {1,4,24}.
Résultat robuste : **0/14 features franchissent la barre** (|t|≥3 cohérent sur ≥3 TFs, signe
stable) ; le meilleur atteint 2 TFs. Points clés : dcor n'apporte RIEN au-delà de Pearson —
dcor_excess (part non-linéaire pure) plafonne à |t| 2.8, ne franchit 3 nulle part ; dcor_btc_eth
monte à |t| 13.2 mais sur un SEUL TF (30m, un régime) ; le λ₂ re-pondéré dcor n'améliore ni le
λ₂ Pearson ni la jambe RMT actuelle, pour un coût ×70 (7 ms vs 0.1 ms) ; nolds prohibitif
(DFA 15 ms, Hurst 17 ms par appel — 4× le coût de tout l'agent, chaque minute) pour un signal
plat ; les pics 1D/1W sont des mirages de petit échantillon (motif [[geometric-mirage-24h]]).
Le baseline confirme la prémisse : à 1H (horizon de PRODUCTION) l'agent est PLAT (t 2.1), et
change de signe aux horizons longs — **son poids bas piloté par EARCP est CORRECT**.
**Verdict : rien à brancher, banc gelé à 14 (§62) inchangé.** Outils installés dispo ailleurs.

Bilan mesure-d'abord : aucun des trois ne justifie de brancher quoi que ce soit en prod
aujourd'hui. Le SEUL fil vivant = la modulation du consensus live par le régime (1c),
+0.12/+0.16 mais 1 bloc — à re-mesurer ~15/07 (journal ≥2 semaines) avant toute décision.
Murs argent, stop −5 %, portes : intouchés (pure mesure).
