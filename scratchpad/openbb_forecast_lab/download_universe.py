"""Télécharge l'historique 8 TF (échelle complète ERR-001) pour le panier
diversifié du probe forecast élargi. SAFE : lecture seule (endpoint public
history-candles USDT-FUTURES), aucun ordre. Écrit dans data_history/ (racine).

Panier = 6 classes DÉCORRÉLÉES (crypto majeurs/alt/meme/DeFi + métaux + actions US).
Poli : pause entre pages + entre symboles, pour ne pas gêner le bot réel.
"""
import sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import candles_history as ch

PANIER = [
    # crypto majeurs
    "BTCUSDT", "ETHUSDT",
    # L1/alt variés
    "SOLUSDT", "XRPUSDT", "BNBUSDT", "TRXUSDT", "ADAUSDT",
    # memecoins
    "DOGEUSDT", "SHIBUSDT", "PEPEUSDT",
    # DeFi/infra
    "LINKUSDT", "UNIUSDT",
    # métaux
    "XAUUSDT", "XAGUSDT",
    # actions US
    "AAPLUSDT", "TSLAUSDT", "NVDAUSDT", "SPYUSDT", "QQQUSDT", "COINUSDT", "MSTRUSDT",
]
# jours à remonter par TF pour viser ~15000 barres (borné par ce que Bitget a).
JOURS = {"1m": 15, "5m": 60, "15m": 180, "30m": 360,
         "1H": 730, "4H": 2600, "1D": 3000, "1W": 3000}

LOG = Path(__file__).resolve().parent / "download_universe.log"


def main():
    fh = LOG.open("w", encoding="utf-8")
    def log(m):
        print(m, flush=True); fh.write(m + "\n"); fh.flush()
    log(f"== téléchargement panier ({len(PANIER)} symboles × 8 TF) ==")
    for sym in PANIER:
        for tf, j in JOURS.items():
            try:
                n = ch.download(sym, tf, jours=j, pause_s=0.25, max_pages=120)
                log(f"  {sym:10} {tf:4} : {n} barres")
            except Exception as e:
                log(f"  {sym:10} {tf:4} : ÉCHEC {type(e).__name__}: {str(e)[:80]}")
            time.sleep(0.4)
    log("== téléchargement terminé ==")
    fh.close()


if __name__ == "__main__":
    main()
