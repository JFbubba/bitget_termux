"""
funding_history.py — historique de FUNDING Bitget (public, paginé, cache disque).
Classement : SAFE. Lecture seule, AUCUN ordre.

§59 : le tier gratuit CoinGlass ne couvre pas l'historique de funding — mais
Bitget l'expose EN PUBLIC (/api/v2/mix/market/history-fund-rate, 100 taux/page,
8 h chacun). C'est la donnée du LIEU D'EXÉCUTION : exactement ce que le carry
encaisse. Débloque : (a) le PERCENTILE de funding courant (SAVOIR.md §5 : passer
le seuil carry d'un absolu à un percentile — ici ADVISORY d'abord) ;
(b) le futur backtest carry.

CLI : python funding_history.py BTCUSDT 3
"""

import json
import time
from pathlib import Path

DOSSIER = Path(__file__).resolve().parent / "data_history"


def _fichier(symbol):
    return DOSSIER / f"FUNDING_{str(symbol).upper()}.json"


def load(symbol="BTCUSDT"):
    """[(ts_ms, taux), ...] triés croissant. [] si rien."""
    try:
        rows = json.loads(_fichier(symbol).read_text(encoding="utf-8"))
        return sorted(rows, key=lambda r: r[0]) if isinstance(rows, list) else []
    except Exception:
        return []


def _page(symbol, page_no, page_size=100):
    try:
        import bitget_market_data as bmd
        rows = bmd._get("/api/v2/mix/market/history-fund-rate",
                        {"symbol": str(symbol).upper(), "productType": "USDT-FUTURES",
                         "pageSize": str(page_size), "pageNo": str(page_no)}) or []
        out = []
        for r in rows:
            try:
                out.append([int(r["fundingTime"]), float(r["fundingRate"])])
            except (KeyError, TypeError, ValueError):
                continue
        return out
    except Exception:
        return []


def download(symbol="BTCUSDT", annees=3, pause_s=0.15, max_pages=40):
    """Consolide l'historique local (dédup par timestamp, écriture atomique).
    ~33 jours/page -> 3 ans ≈ 34 pages. Retourne le nombre total de taux."""
    DOSSIER.mkdir(exist_ok=True)
    borne = int(time.time() * 1000) - int(annees * 365 * 86400_000)
    connu = {r[0]: r for r in load(symbol)}
    for page in range(1, max_pages + 1):
        rows = _page(symbol, page)
        if not rows:
            break
        neuf = [r for r in rows if r[0] not in connu]
        for r in rows:
            connu[r[0]] = r
        if min(r[0] for r in rows) < borne or not neuf:
            break                                 # assez profond, ou plus rien de neuf
        time.sleep(pause_s)
    rows = sorted(connu.values(), key=lambda r: r[0])
    tmp = _fichier(symbol).with_suffix(".json.tmp")
    tmp.write_text(json.dumps(rows), encoding="utf-8")
    import os
    os.replace(tmp, _fichier(symbol))
    return len(rows)


def percentile_taux(rates, taux):
    """Percentile [0,1] d'un taux 8 h dans l'historique. PUR. None si historique
    trop court (< 90 taux ≈ 1 mois)."""
    vals = [r[1] for r in rates or []]
    if len(vals) < 90 or taux is None:
        return None
    return round(sum(1 for v in vals if v <= float(taux)) / len(vals), 4)


def percentile_courant(symbol="BTCUSDT", taux=None):
    """Percentile du taux courant dans l'historique local (best-effort None).
    `taux` = taux 8 h (fraction, ex. 0.0001) ; s'il n'est pas fourni, prend le
    dernier taux de l'historique."""
    rates = load(symbol)
    if taux is None and rates:
        taux = rates[-1][1]
    return percentile_taux(rates, taux)


def build_report(symbol="BTCUSDT"):
    rates = load(symbol)
    lignes = [f"=== FUNDING {symbol} — historique local (lecture seule) ==="]
    if rates:
        import datetime
        utc = datetime.timezone.utc
        d0 = datetime.datetime.fromtimestamp(rates[0][0] / 1000, utc).date()
        dernier = rates[-1][1]
        pct = percentile_taux(rates, dernier)
        apr = dernier * 3 * 365 * 100
        lignes.append(f"{len(rates)} taux 8 h depuis {d0} · dernier {dernier:+.6f} "
                      f"(APR {apr:+.1f} %) · percentile {pct if pct is None else round(100 * pct)}"
                      + ("" if pct is None else " %"))
    else:
        lignes.append("aucun historique — lancer : python funding_history.py")
    lignes.append("Lecture seule. Aucun ordre. VERDICT: SAFE")
    return "\n".join(lignes)


def main():
    import sys
    sym = sys.argv[1] if len(sys.argv) > 1 else "BTCUSDT"
    annees = float(sys.argv[2]) if len(sys.argv) > 2 else 3
    n = download(sym, annees)
    print(build_report(sym))


if __name__ == "__main__":
    main()
