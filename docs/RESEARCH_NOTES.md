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
