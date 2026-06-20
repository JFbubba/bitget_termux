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
