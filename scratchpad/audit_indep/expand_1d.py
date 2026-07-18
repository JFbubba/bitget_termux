"""expand_1d.py — élargit l'univers 1D pour le test de puissance du momentum cross-sectionnel.
Télécharge l'historique 1D (public, lecture seule) de ~35 perps crypto liquides de plus,
au format data_history/{SYM}_1D.json (lu par audit_core). Aucun ordre."""
import sys

sys.path.insert(0, "/root/bitget_termux_repo")
import candles_history as ch

NEW = ["AVAXUSDT", "DOTUSDT", "LTCUSDT", "BCHUSDT", "ATOMUSDT", "NEARUSDT", "APTUSDT",
       "ARBUSDT", "OPUSDT", "FILUSDT", "ICPUSDT", "INJUSDT", "SUIUSDT", "SEIUSDT",
       "TIAUSDT", "RUNEUSDT", "AAVEUSDT", "MKRUSDT", "LDOUSDT", "ETCUSDT", "XLMUSDT",
       "ALGOUSDT", "VETUSDT", "HBARUSDT", "GRTUSDT", "SANDUSDT", "AXSUSDT", "IMXUSDT",
       "WLDUSDT", "FETUSDT", "ONDOUSDT", "STXUSDT", "GALAUSDT", "CHZUSDT", "POLUSDT"]

ok = 0
for s in NEW:
    try:
        n = ch.download(s, "1D", jours=2500, pause_s=0.1, max_pages=60)
        print(f"{s}: {n} barres 1D", flush=True)
        if n > 300:
            ok += 1
    except Exception as e:
        print(f"{s}: ERR {type(e).__name__} {e}", flush=True)
print(f"\n{ok}/{len(NEW)} coins avec >300 barres 1D. Lecture seule, aucun ordre.", flush=True)
