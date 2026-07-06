# =========================
# BITGET LOCAL AGENT CONFIG
# =========================

# Marché
PRODUCT_TYPE = "USDT-FUTURES"
TIMEFRAME = "15m"
CANDLE_LIMIT = 100

SYMBOLS = [
    "BTCUSDT",
    "ETHUSDT",
    "SOLUSDT",
    "XRPUSDT",
    "XAUTUSDT",
]

# === Univers d'analyse DYNAMIQUE (universe.py) ===
# False = on analyse uniquement SYMBOLS ci-dessus (historique). True = univers top-N
# construit à chaque cycle : paires Bitget les plus liquides (volume 24h) filtrées par
# le top market-cap CoinGecko (qualité), ancres SYMBOLS toujours incluses.
DYNAMIC_UNIVERSE = False
UNIVERSE_TOP_N = 20                         # nombre de paires dynamiques (hors ancres)
UNIVERSE_MIN_VOLUME_USDT = 5_000_000       # volume 24h minimal (anti-illiquide)

# Capital / risque
DEFAULT_PAPER_EQUITY_USDT = 100.0
RISK_PER_TRADE_PERCENT = 1.0
MAX_IMPLIED_LEVERAGE = 2.0

# === Limites de risque : SOURCE UNIQUE (réconciliation audit #4) ===
# risk_manager (gate par-ordre) ET risk_limits (caps portefeuille) lisent ces valeurs.
# risk_manager peut surcharger par .env (RISK_MAX_*). Valeurs conservatrices.
MAX_LEVERAGE = MAX_IMPLIED_LEVERAGE        # cap de levier UNIQUE (= 2.0)
MAX_OPEN_POSITIONS = 3                      # positions simultanées (gate par-ordre = cap portefeuille)
MAX_POSITION_USD = 50.0                     # notionnel max d'UNE position
MAX_DAILY_LOSS_USD = 25.0                   # perte journalière réalisée -> halte
MAX_TOTAL_NOTIONAL_USDT = 300.0            # notionnel AGRÉGÉ max (portefeuille)
MAX_TOTAL_RISK_PERCENT = 5.0               # risque cumulé max (%)
MIN_SL_DISTANCE_PERCENT = 0.20             # distance stop minimale (anti dust-stop)

# === Accumulation BTC (spot DCA, paper) — s'AJOUTE au bot futures ===
DCA_BASE_USD = 10.0                         # achat DCA de base par intervalle
DCA_MAX_MULTIPLIER = 5.0                    # renfort max quand l'opportunité est maximale
DCA_INTERVAL_H = 24.0                       # un achat au plus toutes les 24 h

# === MANDAT DE GESTION (politique du bot autonome) — lu par mandate.py ===
# Traduit les choix du propriétaire en RÈGLES DURES. « Au bot de gérer comme un
# pro » = discipline encodée, PAS d'absence de limite. Le réel se débloque par
# paliers : spot d'abord, futures agent-par-agent quand l'edge passe le seuil.
MANDATE_CAPITAL_USDT = 1000.0              # capital de départ confié
MANDATE_TARGET = "MAX"                     # objectif : maximiser le rendement...
MANDATE_MAX_DRAWDOWN_PCT = 20.0            # ...SOUS contrainte : halte dure à -20 % (MDD 15-25 %)
MANDATE_MAX_LEVERAGE = 5.0                 # MUR de levier (le bot ajuste SOUS ce plafond)
MANDATE_RISK_PER_TRADE_PCT = 0.75          # risque ~0,5-1 %/trade (vol-targeting au-dessus)
MANDATE_CASH_FLOOR_PCT = 10.0              # réserve cash plancher (jamais 100 % déployé)
MANDATE_BENCHMARK = "ABSOLUTE"             # benchmark absolu, horizon perpétuel
# Porte d'edge paper -> réel (futures) : un agent ne trade en RÉEL que s'il bat ça.
MANDATE_FUTURES_DSR_MIN = 0.90             # Deflated Sharpe Ratio minimal (multiple-testing)
MANDATE_FUTURES_MIN_SAMPLES = 120          # taille d'échantillon minimale (anti faux-positif)
# Exécution FUTURES réelle (§45) — les CAPS effectifs sont définis UNE SEULE fois,
# plus bas (section « FUTURES RÉEL ») : le doublon historique §34 (10/20) a été
# retiré à l'audit du 03/07 — éditer une 1re occurrence écrasée par la 2e ne
# faisait silencieusement rien.
FUTURES_AUTONOMOUS_LIVE = False             # 2e verrou futures (armé via .env, avec MANDATE_LIVE_ENABLED)
FUTURES_REAL_LEDGER = "futures_real_ledger.json"   # journal exécuteur : events DRY ET RÉELS (gitignored)
# Numéraire dynamique : si le dollar se déprécie, tourner hors USD vers ces refuges.
MANDATE_NUMERAIRE_REFUGES = ["BTCUSDT", "XAUTUSDT"]   # BTC, or tokenisé
MANDATE_USD_WEAK_THRESHOLD = -3.0          # baisse % du DXY (fenêtre) déclenchant la rotation
# Sessions actives (UTC) : ouvertures Asie / Londres / New York (+ garde slippage).
MANDATE_ACTIVE_SESSIONS_UTC = [[0, 3], [7, 10], [13, 17]]
# Black-out macro autour des annonces à fort impact (CPI, FOMC) : dégager le risque.
MANDATE_MACRO_BLACKOUT_PRE_MIN = 30        # minutes AVANT l'annonce
MANDATE_MACRO_BLACKOUT_POST_MIN = 15       # minutes APRÈS
# Verrou réel : True = exécution réelle AUTORISÉE (achat spot BTC via spot_executor,
# manuel/confirmé). N'arme PAS l'autonome : l'accumulation reste paper tant qu'elle
# n'est pas câblée à l'exécution (test-first). Futures toujours bloqué (échelle d'edge).
MANDATE_LIVE_ENABLED = True

# Accumulation RÉELLE (achat spot BTC) — plafonds DURS lus par spot_executor.py.
ACCUM_REAL_MAX_PER_BUY_USDT = 5.0          # plafond dur par achat réel
ACCUM_REAL_MAX_DAILY_USDT = 5.0            # plafond dur journalier (anti-boucle)
# Affûtage TIMING d'entrée (RESEARCH_NOTES §38) : survente court-terme mêlée au score
# d'opportunité. Validé en backtest cost-basis (avantage OOS +0.69%->+0.77%, robuste).
# ACCUM_ST_WEIGHT=0 -> score historique inchangé. Non-directionnel (meilleur point d'entrée).
ACCUM_ST_WEIGHT = 0.30                      # poids de la survente court-terme (0 = désactivé)
ACCUM_ST_WINDOW = 24                        # fenêtre (barres) de la moyenne mobile courte
# Style d'exécution de l'achat spot : "limit_ioc" (DÉFAUT, validé en réel) = limite IOC
# plafonnée -> remplit tout de suite SANS slippage au-delà du plafond ; "taker" = marché ;
# "maker" = limite post-only au bid (frais maker / meilleur prix mais peut ne pas remplir).
# Surchargeable via .env (EXEC_STYLE=taker pour revenir au marché).
EXEC_STYLE = "limit_ioc"
ACCUM_SLIPPAGE_TOL_PCT = 0.10              # plafond de slippage (%) au-dessus de l'ask pour limit_ioc

# 2e verrou : accumulation AUTONOME réelle (DCA auto dans le cycle). DOUBLE verrou avec
# MANDATE_LIVE_ENABLED. False = l'accumulation reste paper même verrou global levé.
# À lever MANUELLEMENT après quelques achats manuels d'observation.
ACCUM_AUTONOMOUS_LIVE = False

# Garde « meilleur prix » : n'accumule PAS si Bitget cote au-dessus de la médiane
# cross-exchange de plus de ce % (premium). Évite d'acheter sur un pic propre à Bitget.
ACCUM_MAX_PREMIUM_PCT = 0.30

# === Porte directionnelle régime-aware (regime_gate.py, lue par journal_scanner) ===
# Supprime les signaux qui combattent la marée macro : en RISK_OFF, aucun LONG n'est
# généré/suivi ; en RISK_ON, aucun SHORT (symétrique). Motivé par les résultats
# mesurés (LONG ~18 % WR en peur extrême). Analyse seule — AUCUN ordre. Fail-safe :
# régime indisponible -> NEUTRE -> porte transparente (comportement historique).
REGIME_GATE_ENABLED = True          # False = restaure l'ancien comportement sans toucher au code
REGIME_GATE_USE_SENTIMENT = True    # l'extrême Fear&Greed PRIME sur le macro (peur -> RISK_OFF)
REGIME_GATE_FNG_FEAR = 20           # F&G <= seuil -> RISK_OFF effectif (coupe les LONG, même si macro RISK_ON)
REGIME_GATE_FNG_GREED = 80          # F&G >= seuil -> RISK_ON effectif (coupe les SHORT, même si macro RISK_OFF)

# === Carry non-directionnel (carry_monitor.py, PAPER — mesure, n'exécute rien) ===
# Le cash-and-carry (long spot + short perp, delta-neutre) encaisse le funding sans
# parier sur la direction — la seule famille de rendement qui ne suppose aucun edge
# directionnel (RESEARCH_NOTES §35-38 : pas d'edge directionnel robuste).
CARRY_FRAIS_ALLER_RETOUR_PCT = 0.20   # frais estimés entrée+sortie (2 jambes spot+perp, %)
CARRY_SEUIL_APR_PCT = 5.0             # APR net annualisé au-dessus duquel le carry est jugé ATTRACTIF

# === Cerveau : bornes DURES des poids d'agents (swarm_brain._clamp_weights) ===
# Empêche un agent de dominer artificiellement le consensus (bug : la normalisation
# post-EARCP court-circuitait le clamp historique 0.2..3.0).
BRAIN_WEIGHT_MIN = 0.2
BRAIN_WEIGHT_MAX = 3.0

# === Cerveau : priors d'edge ADVISORY (edge_ladder -> poids EARCP, §40) ===
# L'edge MESURÉ borne l'edge APPRIS : les poids EARCP sont multipliés par
# prior**ALPHA (adouci), renormalisés (moy ~1) puis re-bornés. Un agent à l'IC live
# significativement NÉGATIF est bridé même si sa cohérence de consensus le flatte.
BRAIN_EDGE_PRIORS = 1                 # 0 = débrayer (poids EARCP purs)
BRAIN_EDGE_PRIOR_ALPHA = 0.5          # adoucissement (1.0 = prior plein, 0.0 = neutre)
BRAIN_VOTES_WORKERS = 8
# §63 — cadence scan 1 min (demande propriétaire) : constantes de TEMPS compensées.
BRAIN_LOG_CAP = 2400                  # fenêtre roulante ~5 h à 480 entrées/h (maturation 1 h garantie)
BRAIN_HITRATE_ALPHA = 0.01            # EWMA hit-rates : même demi-vie (~14 h) qu'à 5 min
BRAIN_EARCP_LISSAGE = 0.02            # lissage vers la cible : même vitesse horaire qu'avant               # threads de gather_votes (agents = I/O réseau ; 1 = séquentiel)

# === FUTURES RÉEL (§45 — décision propriétaire du 02/07/2026) ===
# Le propriétaire a changé les règles (3 questions d'engagement répondues) : futures
# réel autorisé (carry + directionnel), directement en réel, plafond = solde futures.
# La porte d'edge est OUTREPASSÉE en connaissance de cause (0 agent LIVE) — remettre
# FUTURES_EDGE_GATE_OVERRIDE=0 la referme instantanément. Les caps effectifs démarrent
# BAS (montée progressive si l'exécution est propre) ; murs absolus en dur dans
# futures_executor : 50 $/trade, 250 $ cumulé, infranchissables par env/config.
FUTURES_EDGE_GATE_OVERRIDE = 1        # 0 = re-fermer la porte d'edge (retour à la preuve)
FUTURES_REAL_MAX_PER_TRADE_USDT = 50.0   # cap effectif par ordre = mur dur (décision propriétaire 03/07, cap carry 200)
FUTURES_REAL_MAX_GROSS_USDT = 200.0      # cap effectif exposition cumulée (mur dur : 250 ; décision propriétaire 03/07)
FUTURES_DAILY_LOSS_STOP_PCT = 5.0        # perte journalière -> kill-switch (fail-closed)
# RE-BASELINE sur flux de capital : un saut du LIVRE d'un tick à l'autre > ce % de
# l'ouverture est impossible en P&L de trading borné (murs 50/250, progressif) -> c'est
# un dépôt/retrait/CONVERT (ex. conversion BGBTC 05/07 : -161$ -> faux breach). On décale
# alors la baseline du montant du flux : le stop mesure le P&L, pas les mouvements de fonds.
FUTURES_BOOK_CLIFF_REBASE_PCT = 15.0
# Boucle directionnelle automatique (futures_auto, §45) — décide, délègue à l'exécuteur.
FUTURES_AUTO_DIRECTIONAL = 1          # 0 = débrayer la boucle (aucune décision d'ordre)
FUTURES_AUTO_NOTIONAL_USDT = 10.0     # taille d'ouverture (≤ cap/trade 15, murs 50)
FUTURES_AUTO_LEVERAGE = 2.0           # levier demandé (mur ×5)
FUTURES_AUTO_SEUIL_ENTREE = 0.35      # |consensus| minimal pour OUVRIR (conviction rare)
FUTURES_AUTO_SEUIL_SORTIE = 0.15      # |consensus| sous lequel on FERME (conviction morte)
FUTURES_AUTO_MIN_INTERVAL_H = 4.0     # au plus un ordre auto toutes les N heures
FUTURES_AUTO_MAX_POSITIONS = 3        # positions directionnelles simultanées max (multi-symboles §47,
                                      # une par symbole ; aligné sur MAX_OPEN_POSITIONS)
FUTURES_MARGE_ALERTE_DIST_PCT = 15.0
FUTURES_FUNDING_TIMING_MIN = 20       # report d'OUVERTURE si un règlement de funding tombe
                                      # dans N min et que le côté paierait (§60, SAVOIR §5)  # tripwire : alerte si une position est à < N % de son prix
                                      # de liquidation (marge croisée, positions §47 empilées)
FUTURES_AUTO_SL_PCT = 1.5             # stop-loss % du prix si ATR indisponible
FUTURES_AUTO_RR = 2.0                 # take-profit = distance SL × RR

# Jambes cash-and-carry automatiques (carry_auto, §45) — short perp COUVERT par le
# BTC spot détenu (delta-neutre, levier ×1, sans SL : hedgé). Entrée : ATTRACTIF
# (carry_monitor, seuil 5 %) ; sortie par hystérésis sous le seuil ci-dessous.
FUTURES_AUTO_CARRY = 1                # 0 = débrayer les jambes carry
FUTURES_CARRY_NOTIONAL_USDT = 200.0   # cible carry (décision propriétaire 03/07) — toujours ≤ 95 % de la couverture spot, montée par TRANCHES ≤ cap/trade toutes les 8 h
FUTURES_CARRY_SEUIL_SORTIE_PCT = 2.0  # APR net sous lequel on FERME (hystérésis vs 5 %)
FUTURES_CARRY_MIN_INTERVAL_H = 8.0    # une action carry max par période de funding
# Couverture de la jambe carry : tokens du portefeuille comptant comme exposition
# BTC, avec décote (wrapper BGBTC décoté 10 % — prudence dé-peg/conversion).
CARRY_COUVERTURE_TOKENS = {"BTC": 1.0, "BGBTC": 0.9}

FUTURES_POSITION_MODE = "hedge_mode"  # mode CIBLE (déclaré par le propriétaire 03/07) : long ET short
                                      # simultanés (carry + directionnel). ADAPTATIF : une position
                                      # OUVERTE fait autorité (Bitget refuse de basculer en position) ;
                                      # la bascule s'applique au premier ordre à plat.
FUTURES_EXEC_STYLE = "limit_ioc"      # ouvertures : limit IOC plafonné (anti-slippage) ; "market" = brut
FUTURES_SLIPPAGE_TOL_PCT = 0.10       # plafond de slippage des ouvertures (% au-delà du mark)
FUTURES_MARGIN_MODE = "isolated"         # perte max d'une position = sa marge ; ADAPTATIF :
                                         # compte en mode multi-devises (assetMode union,
                                         # constaté le 02/07) -> crossed FORCÉ (Bitget
                                         # interdit l'isolé en union) — resolve_marge_mode

# === Accumulation RÉELLE : sizing proportionnel à l'opportunité (§44) ===
# montant réel = cap·(FLOOR + (1−FLOOR)·score) ∈ [2, 5] $ avec cap 5 : restaure
# l'edge de sizing validé (§38) que le clamp plat à 5 $ neutralisait. Décision
# propriétaire du 02/07. FLOOR=1.0 -> retour au 5 $ plat.
ACCUM_FENETRE_DEBUT_H = 16.0          # fenêtre d'achat DCA (UTC) : 16-19h mesurées ~10 bps
ACCUM_FENETRE_FIN_H = 20.0            # moins chères que 12h sur 1 an de bougies 1h (§53)
ACCUM_REAL_FLOOR_FRAC = 0.4
ACCUM_RUNWAY_ALERT_USDT = 15.0        # alerte réapprovisionnement quand l'USDT spot libre passe dessous

# Stratégie
EMA_FAST = 9
EMA_SLOW = 21
RSI_PERIOD = 14
ATR_PERIOD = 14
ATR_STOP_MULTIPLIER = 1.5
RISK_REWARD_RATIO = 2.0

# Hedge mode
HEDGE_MODE = True
MAX_SAME_SIDE_POSITION_PER_SYMBOL = 1

# Boucle
LOOP_INTERVAL_SECONDS = 15 * 60

# Fichiers
SIGNALS_JOURNAL_FILE = "signals_journal.csv"
OPEN_STATE_FILE = "open_outcomes_state.csv"
FINAL_OUTCOMES_FILE = "final_outcomes_journal.csv"

# === Agent LLM (15ᵉ agent, OPT-IN) — llm_agent.py, décision propriétaire 06/07/2026 ===
# Surcouche non-déterministe au banc gelé à 14 (§62). DÉFAUT OFF : tant que
# LLM_AGENT_ENABLED est False, le cerveau se comporte à l'identique. FAIL-SAFE (LLM
# indispo/lent/incohérent -> vote ignoré). N'a AUCUN pouvoir sur les murs de guards().
LLM_AGENT_ENABLED = False                  # interrupteur maître (armer via .env aussi)
LLM_AGENT_BACKEND = "local"                # "local" = Ollama VPS (rien ne sort) ; "cloud" = OpenRouter
LLM_AGENT_MODEL_LOCAL = "qwen2.5:7b"       # modèle Ollama local (localhost:11434)
LLM_AGENT_MODEL_CLOUD = "openai/gpt-5-mini"  # modèle OpenRouter (OPENROUTER_API_KEY dans .env)
LLM_AGENT_MODEL_GEMINI = "gemini-2.5-flash"  # modèle Google AI Studio direct (backend "gemini", GEMINI_API_KEY)
LLM_AGENT_GEMINI_THINKING = 0              # budget raisonnement Gemini (0 = coupé -> vote rapide, tient dans max_tokens)
LLM_AGENT_TIMEOUT_S = 8.0                  # au-delà -> vote ignoré (ne ralentit pas le cerveau)
LLM_AGENT_MAX_TOKENS = 800                 # budget sortie cloud (modèles thinking : marge de raisonnement)
LLM_AGENT_CONF_CAP = 0.5                   # plafond de confiance (ne domine pas le banc)
LLM_AGENT_WEIGHT = 0.5                     # poids FIXE dans l'agrégation (non appris, non persisté)
LLM_AGENT_SYMBOLS = ""                      # liste blanche (ex. "BTCUSDT") ; vide = TOUS les tokens de l'univers
LLM_AGENT_TTL_S = 900                       # vote LLM caché/symbole (15 min) : couvre tout l'univers sans exploser le quota
LLM_AGENT_KEEPALIVE = "30m"                 # Ollama : garde qwen en mémoire entre cycles (évite le rechargement swap)
