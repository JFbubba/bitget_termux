"""Complément d'historique pour l'échelle COMPLÈTE de timeframes (ERR-001).
LECTURE SEULE : endpoint public history-candles via candles_history.download
(GET poli, pause 0.15 s/page). Écrit uniquement dans data_history/ (cache
disque standard du dépôt, gitignored). AUCUN ordre.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import candles_history as ch  # noqa: E402

# (symbole, granularité, jours demandés) — profondeur RÉELLE annotée après coup.
TACHES = [
    ("BTCUSDT", "1m", 60), ("ETHUSDT", "1m", 60),          # M1 : profondeur API limitée
    ("BTCUSDT", "15m", 365), ("ETHUSDT", "15m", 365),       # M15
    ("BTCUSDT", "30m", 365), ("ETHUSDT", "30m", 365),       # M30
    ("BTCUSDT", "4H", 2200), ("ETHUSDT", "4H", 2200),       # H4 ~6 ans
    ("BTCUSDT", "1W", 2200), ("ETHUSDT", "1W", 2200),       # W1 ~6 ans
]

for sym, gran, jours in TACHES:
    try:
        n = ch.download(sym, gran, jours)
        rows = ch.load(sym, gran)
        if rows:
            import datetime
            utc = datetime.timezone.utc
            d0 = datetime.datetime.fromtimestamp(rows[0][0] / 1000, utc).date()
            d1 = datetime.datetime.fromtimestamp(rows[-1][0] / 1000, utc).date()
            print(f"{sym} {gran}: {n} bougies ({d0} -> {d1})", flush=True)
        else:
            print(f"{sym} {gran}: 0 bougie", flush=True)
    except Exception as exc:  # jamais bloquant
        print(f"{sym} {gran}: ECHEC {exc}", flush=True)
print("TELECHARGEMENT TERMINE")
