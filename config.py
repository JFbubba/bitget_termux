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
