"""
candles_history.py — historique PROFOND de bougies (paginé, cache disque incrémental).
Classement : SAFE. Lecture seule (endpoint public), AUCUN ordre.

Pourquoi (§53) : l'API ne sert que ~1000 bougies par requête (41 j en 1h) — trop
court pour juger une stratégie. Ce module pagine EN ARRIÈRE via endTime et
consolide sur disque (data_history/, gitignored) : le backtest directionnel long,
la faisabilité des paires co-intégrées et la saisonnalité du DCA (feuille de
route §52) se mesurent sur des mois, pas des semaines.

CLI : python candles_history.py BTCUSDT 1h 365     (télécharge/complète 365 jours)
"""

import json
import time
from pathlib import Path

DOSSIER = Path(__file__).resolve().parent / "data_history"
# granularités MIX (futures) : 1H/4H/1D en MAJUSCULE (le minuscule est l'énum spot)
GRAN_MS = {"1m": 60_000, "5m": 300_000, "15m": 900_000, "30m": 1_800_000,
           "1H": 3_600_000, "4H": 14_400_000, "1D": 86_400_000, "1W": 604_800_000}


def _norm_gran(g):
    """'1h' -> '1H' (convention mix). Pur."""
    g = str(g).strip()
    return g.upper() if g and g[-1] in "hdw" else g


def _fichier(symbol, gran):
    return DOSSIER / f"{str(symbol).upper()}_{_norm_gran(gran)}.json"


def _page(symbol, gran, end_ms, limit=200):
    """Une page de bougies finissant à end_ms (endpoint public history-candles,
    lecture seule, va loin dans le passé). [] si indisponible."""
    try:
        import bitget_market_data as bmd
        rows = bmd._get("/api/v2/mix/market/history-candles", {
            "symbol": str(symbol).upper(), "productType": "USDT-FUTURES",
            "granularity": _norm_gran(gran), "endTime": str(int(end_ms)),
            "limit": str(int(limit))}) or []
        out = []
        for r in rows:
            try:
                out.append([int(r[0]), float(r[1]), float(r[2]), float(r[3]),
                            float(r[4]), float(r[5])])
            except (TypeError, ValueError, IndexError):
                continue
        return out
    except Exception:
        return []


def load(symbol, gran="1h"):
    """Bougies consolidées du disque, triées par ts. [] si rien."""
    try:
        rows = json.loads(_fichier(symbol, gran).read_text(encoding="utf-8"))
        return sorted(rows, key=lambda r: r[0]) if isinstance(rows, list) else []
    except Exception:
        return []


def download(symbol, gran="1h", jours=365, pause_s=0.15, max_pages=400):
    """Complète l'historique local jusqu'à `jours` en arrière (incrémental, dédup
    par timestamp, écriture atomique). Retourne le nombre total de bougies."""
    DOSSIER.mkdir(exist_ok=True)
    pas = GRAN_MS.get(_norm_gran(gran), 3_600_000)
    borne = int(time.time() * 1000) - jours * 86_400_000
    connu = {r[0]: r for r in load(symbol, gran)}
    end = int(time.time() * 1000)
    if connu:                                     # reprend derrière le plus ancien connu
        plus_ancien = min(connu)
        if plus_ancien <= borne:
            end = None                            # déjà assez profond côté passé
        else:
            end = plus_ancien - 1
    pages = 0
    while end is not None and end > borne and pages < max_pages:
        rows = _page(symbol, gran, end)
        pages += 1
        if not rows:
            break
        for r in rows:
            connu[r[0]] = r
        anciennete = min(r[0] for r in rows)
        if anciennete >= end:                     # plus de progrès -> stop
            break
        end = anciennete - 1
        time.sleep(pause_s)
    # complète aussi le RÉCENT (depuis le plus jeune connu jusqu'à maintenant)
    if connu:
        plus_jeune = max(connu)
        while plus_jeune < int(time.time() * 1000) - 2 * pas and pages < max_pages:
            rows = _page(symbol, gran, plus_jeune + 200 * pas)
            pages += 1
            neuf = [r for r in rows if r[0] > plus_jeune]
            if not neuf:
                break
            for r in neuf:
                connu[r[0]] = r
            plus_jeune = max(connu)
            time.sleep(pause_s)
    rows = sorted(connu.values(), key=lambda r: r[0])
    tmp = _fichier(symbol, gran).with_suffix(".json.tmp")
    tmp.write_text(json.dumps(rows), encoding="utf-8")
    import os
    os.replace(tmp, _fichier(symbol, gran))
    return len(rows)


def main():
    import sys
    sym = sys.argv[1] if len(sys.argv) > 1 else "BTCUSDT"
    gran = sys.argv[2] if len(sys.argv) > 2 else "1h"
    jours = int(sys.argv[3]) if len(sys.argv) > 3 else 365
    n = download(sym, gran, jours)
    rows = load(sym, gran)
    if rows:
        import datetime
        utc = datetime.timezone.utc
        d0 = datetime.datetime.fromtimestamp(rows[0][0] / 1000, utc).date()
        d1 = datetime.datetime.fromtimestamp(rows[-1][0] / 1000, utc).date()
        print(f"{sym} {gran} : {n} bougies consolidées ({d0} -> {d1}). "
              "Lecture seule, aucun ordre. VERDICT: SAFE")
    else:
        print(f"{sym} {gran} : aucune donnée. VERDICT: SAFE")


if __name__ == "__main__":
    main()
