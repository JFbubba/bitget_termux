"""bitget_explorer.py — explorateur LECTURE SEULE de l'API Bitget pour le dashboard.

Classement : SAFE.
  - sections WHITELISTÉES uniquement : consultation du compte (GET signés) et données
    de marché publiques. AUCUN ordre, AUCUNE écriture, AUCUN retrait, AUCUN virement.
  - réutilise les lecteurs déjà audités du dépôt (real_positions pour les GET signés,
    futures_report pour fills/bills via l'Agent Hub, bitget_announcements) ;
  - chaque section est best-effort : erreur -> {"ok": False, "erreur": ...} lisible,
    le dashboard affiche le message au lieu de casser.

CLI : python bitget_explorer.py [section] [symbole]
"""
import time

import requests

BASE_URL = "https://api.bitget.com"


def _num(x, default=0.0):
    try:
        return float(x)
    except (TypeError, ValueError):
        return default


def _get_public(path, params=None, timeout=10):
    """GET public (sans clé). Lève sur erreur réseau/HTTP/code API."""
    r = requests.get(BASE_URL + path, params=params or {}, timeout=timeout)
    r.raise_for_status()
    data = r.json()
    if data.get("code") != "00000":
        raise RuntimeError(f"Bitget {path}: {data.get('msg')}")
    return data.get("data")


def _signed(path, params=None):
    """GET signé de CONSULTATION via le signeur déjà audité de real_positions."""
    import real_positions as rp
    return rp._signed_get(path, params)


def _lister(data, *cles):
    """Extrait une liste d'un retour API tolérant : liste directe, ou dict portant
    l'une des clés candidates (PUR, testable)."""
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for k in cles or ("list", "resultList", "assetList", "fillList", "bills"):
            v = data.get(k)
            if isinstance(v, list):
                return v
    return []


def _curate(rows, keep, limit=25):
    """Ne garde que les colonnes utiles, dans l'ordre demandé (PUR, testable).
    Une valeur None/'' est omise pour alléger le rendu."""
    out = []
    for r in (rows or [])[:limit]:
        if isinstance(r, dict):
            out.append({k: r.get(k) for k in keep if r.get(k) not in (None, "")})
    return out


# --------------------------- sections « compte » --------------------------- #

def _soldes(_symbol):
    """Ventilation officielle du portefeuille par type de compte + total."""
    import real_positions as rp
    bal = rp.all_account_balance()
    rows = [{"compte": k, "usdt": v} for k, v in sorted(
        (bal.get("accounts") or {}).items(), key=lambda kv: -kv[1])]
    rows.append({"compte": "TOTAL", "usdt": bal.get("total_usdt")})
    return rows


def _spot_avoirs(_symbol):
    rows = _lister(_signed("/api/v2/spot/account/assets"))
    rows = [r for r in rows if _num(r.get("available")) + _num(r.get("frozen"))
            + _num(r.get("locked")) > 0]
    return _curate(rows, ("coin", "available", "frozen", "locked", "uTime"))


def _futures_compte(_symbol):
    rows = _lister(_signed("/api/v2/mix/account/accounts",
                           {"productType": "USDT-FUTURES"}))
    return _curate(rows, ("marginCoin", "accountEquity", "available", "locked",
                          "unrealizedPL", "crossedRiskRate", "crossedMaxAvailable"))


def _futures_positions(_symbol):
    import real_positions as rp
    return rp.futures()


def _marge_iso(_symbol):
    import real_positions as rp
    return rp.margin_isolated()


def _marge_croisee(_symbol):
    import real_positions as rp
    return rp.margin_crossed()


def _earn_avoirs(_symbol):
    rows = _lister(_signed("/api/v2/earn/savings/assets"))
    for r in rows:                               # aplatit l'APY imbriqué pour le tableau
        if isinstance(r, dict) and isinstance(r.get("apy"), list) and r["apy"]:
            r["apy"] = (r["apy"][0] or {}).get("currentApy")
    return _curate(rows, ("productCoin", "coin", "holdAmount", "amount",
                          "apy", "productType", "status"))


def _ordres_spot_ouverts(_symbol):
    rows = _lister(_signed("/api/v2/spot/trade/unfilled-orders"))
    return _curate(rows, ("symbol", "side", "orderType", "price", "size",
                          "status", "cTime"))


def _tri_recent(rows, champ="cTime"):
    """Trie du plus récent au plus ancien (PUR — l'ordre d'arrivée des lecteurs
    diffère : fills triés croissants, bills livrés décroissants)."""
    try:
        return sorted(rows or [], key=lambda r: _num((r or {}).get(champ)), reverse=True)
    except Exception:
        return list(rows or [])


def _fills_futures(_symbol):
    """Fills futures récents du compte (via futures_report, déjà audité — Agent Hub)."""
    import futures_report as fr
    rows = _tri_recent(fr.fetch_fills(limit=40))[:25]
    return _curate(rows, ("symbol", "side", "price", "baseVolume", "quoteVolume",
                          "profit", "tradeScope", "cTime"))


def _bills_futures(_symbol):
    """Écritures du compte futures (frais, funding, PnL — via futures_report)."""
    import futures_report as fr
    rows = _tri_recent(fr.fetch_bills(limit=60))[:25]
    return _curate(rows, ("symbol", "amount", "fee", "businessType", "coin", "cTime"))


# --------------------------- sections « marché » --------------------------- #

def _tickers_spot(_symbol):
    rows = _lister(_get_public("/api/v2/spot/market/tickers"))
    rows.sort(key=lambda r: -_num(r.get("usdtVolume")))
    return _curate(rows[:20], ("symbol", "lastPr", "change24h", "high24h",
                               "low24h", "usdtVolume"))


def _tickers_futures(_symbol):
    rows = _lister(_get_public("/api/v2/mix/market/tickers",
                               {"productType": "USDT-FUTURES"}))
    rows.sort(key=lambda r: -_num(r.get("usdtVolume")))
    return _curate(rows[:20], ("symbol", "lastPr", "change24h", "fundingRate",
                               "holdingAmount", "usdtVolume"))


def _funding(symbol):
    data = _get_public("/api/v2/mix/market/current-fund-rate",
                       {"symbol": symbol, "productType": "USDT-FUTURES"})
    rows = _lister(data)
    if not rows and isinstance(data, dict):
        rows = [data]
    return _curate(rows, ("symbol", "fundingRate", "fundingRateInterval", "nextUpdate"))


def _open_interest(symbol):
    data = _get_public("/api/v2/mix/market/open-interest",
                       {"symbol": symbol, "productType": "USDT-FUTURES"})
    rows = _lister(data, "openInterestList")
    return _curate(rows, ("symbol", "size", "amount"))


def _annonces(_symbol):
    import bitget_announcements as ba
    rows = ba.fetch_announcements() or []
    return _curate(rows, ("title", "type", "score", "ts", "url"), limit=15)


# section -> (libellé, catégorie, producteur). L'ORDRE est celui du sélecteur.
SECTIONS = {
    "soldes":            ("Portefeuille — ventilation par compte", "compte", _soldes),
    "spot_avoirs":       ("Spot — avoirs par coin",                "compte", _spot_avoirs),
    "futures_compte":    ("Futures — compte USDT-M",               "compte", _futures_compte),
    "futures_positions": ("Futures — positions ouvertes",          "compte", _futures_positions),
    "marge_iso":         ("Marge isolée — avoirs/emprunts",        "compte", _marge_iso),
    "marge_croisee":     ("Marge croisée — avoirs/emprunts",       "compte", _marge_croisee),
    "earn_avoirs":       ("Earn — avoirs placés",                  "compte", _earn_avoirs),
    "ordres_spot":       ("Spot — ordres ouverts",                 "compte", _ordres_spot_ouverts),
    "fills_futures":     ("Futures — derniers fills",              "compte", _fills_futures),
    "bills_futures":     ("Futures — écritures (frais/funding)",   "compte", _bills_futures),
    "tickers_spot":      ("Tickers spot — top volume",             "marché", _tickers_spot),
    "tickers_futures":   ("Tickers futures — top volume",          "marché", _tickers_futures),
    "funding":           ("Funding courant (symbole affiché)",     "marché", _funding),
    "open_interest":     ("Open interest (symbole affiché)",       "marché", _open_interest),
    "annonces":          ("Annonces Bitget (scorées)",             "marché", _annonces),
}


def sections():
    """Liste des sections pour le sélecteur du dashboard (PUR)."""
    return [{"key": k, "label": lbl, "cat": cat}
            for k, (lbl, cat, _fn) in SECTIONS.items()]


def fetch(key, symbol="BTCUSDT"):
    """Récupère UNE section whitelistée. Best-effort : jamais d'exception qui remonte."""
    spec = SECTIONS.get(str(key or ""))
    if not spec:
        return {"ok": False, "erreur": f"section inconnue : {key!r}",
                "sections": [s["key"] for s in sections()]}
    label, cat, fn = spec
    try:
        rows = fn(str(symbol or "BTCUSDT").upper()) or []
        return {"ok": True, "key": key, "label": label, "cat": cat,
                "rows": rows, "n": len(rows), "ts": int(time.time())}
    except Exception as exc:                     # noqa: BLE001 — best-effort par contrat
        return {"ok": False, "key": key, "label": label, "cat": cat,
                "erreur": f"{type(exc).__name__}: {exc}"}


def main():
    import json
    import sys
    key = sys.argv[1] if len(sys.argv) > 1 else "soldes"
    symbol = sys.argv[2].upper() if len(sys.argv) > 2 else "BTCUSDT"
    print(json.dumps(fetch(key, symbol), indent=2, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()
