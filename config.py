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
# Numéraire dynamique : si le dollar se déprécie, tourner hors USD vers ces refuges.
MANDATE_NUMERAIRE_REFUGES = ["BTCUSDT", "XAUTUSDT"]   # BTC, or tokenisé
MANDATE_USD_WEAK_THRESHOLD = -3.0          # baisse % du DXY (fenêtre) déclenchant la rotation
# Sessions actives (UTC) : ouvertures Asie / Londres / New York (+ garde slippage).
MANDATE_ACTIVE_SESSIONS_UTC = [[0, 3], [7, 10], [13, 17]]
# Black-out macro autour des annonces à fort impact (CPI, FOMC) : dégager le risque.
MANDATE_MACRO_BLACKOUT_PRE_MIN = 30        # minutes AVANT l'annonce
MANDATE_MACRO_BLACKOUT_POST_MIN = 15       # minutes APRÈS
# Verrou réel : tant que False, AUCUN ordre réel — tout reste paper (DRY_RUN).
MANDATE_LIVE_ENABLED = False               # à lever MANUELLEMENT après rotation des clés + MCP

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
