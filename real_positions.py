"""
real_positions.py — positions RÉELLES en cours (spot · marge isolée · marge croisée ·
futures). LECTURE SEULE.

Classement : SAFE. Uniquement des GET signés de CONSULTATION (soldes/positions du
compte réel) — AUCUN ordre, aucune écriture, aucun retrait. Réutilise le signeur de
`bitget_balance_reader` (clé Bitget = Trade only, jamais de retrait). Chaque catégorie
est best-effort : une erreur/endpoint vide -> liste vide, jamais d'exception qui
remonte (le dashboard reste debout).

Catégories (« trades en cours ») :
  • spot          : avoirs spot valorisés (coin détenu = position spot ouverte) ;
  • margin_iso    : marge ISOLÉE par symbole (emprunt actif = trade à effet de levier) ;
  • margin_cross  : marge CROISÉE par coin (emprunt actif) ;
  • futures       : positions perp USDT-M ouvertes (sens, taille, entrée, PnL, levier,
                    mode de marge isolated/crossed).

CLI : python real_positions.py
"""
import time
from urllib.parse import urlencode

import requests

import bitget_balance_reader as br

BASE_URL = "https://api.bitget.com"
DUST_USDT = 1.0                     # seuil anti-poussière pour les avoirs spot/marge


def _signed_get(path, params=None, timeout=10):
    """GET signé (lecture seule) via le signeur de bitget_balance_reader. Lève sur
    erreur réseau/HTTP ; l'appelant enveloppe en best-effort."""
    key, secret, pw = br.load_keys()
    params = params or {}
    qs = urlencode(params)
    ts = str(int(time.time() * 1000))
    sig = br.create_signature(secret, ts, "GET", path, qs, "")
    headers = {"ACCESS-KEY": key, "ACCESS-SIGN": sig, "ACCESS-TIMESTAMP": ts,
               "ACCESS-PASSPHRASE": pw, "locale": "en-US", "Content-Type": "application/json"}
    r = requests.get(BASE_URL + path, headers=headers, params=params, timeout=timeout)
    r.raise_for_status()
    data = r.json()
    if data.get("code") != "00000":
        raise RuntimeError(f"Bitget {path}: {data.get('msg')}")
    return data.get("data") or []


def _num(x, default=0.0):
    try:
        return float(x)
    except (TypeError, ValueError):
        return default


def _prices():
    """Prix marché de tous les symboles (1 requête publique, best-effort {})."""
    try:
        import bitget_market_data as bmd
        return bmd.mark_prices() or {}
    except Exception:
        return {}


def spot(prices=None):
    """Avoirs SPOT valorisés (coin détenu > seuil poussière). Trié par valeur décroissante."""
    prices = prices if prices is not None else _prices()
    out = []
    for row in _signed_get("/api/v2/spot/account/assets"):
        coin = str(row.get("coin") or "").upper()
        amount = _num(row.get("available")) + _num(row.get("frozen")) + _num(row.get("locked"))
        if amount <= 0 or not coin:
            continue
        px = 1.0 if coin in ("USDT", "USDC") else _num(prices.get(coin + "USDT"))
        value = amount * px if px else None
        # exclut la poussière ET les coins non valorisables (délistés/airdrops sans marché)
        if value is None or value < DUST_USDT:
            continue
        out.append({"coin": coin, "amount": round(amount, 8),
                    "price": round(px, 6) if px else None,
                    "value_usdt": round(value, 2) if value is not None else None,
                    "frozen": round(_num(row.get("frozen")) + _num(row.get("locked")), 8)})
    out.sort(key=lambda r: -(r["value_usdt"] or 0))
    return out


def _margin_rows(path, key_field):
    """Positions marge (iso/cross) : ne garde que les lignes AVEC un emprunt actif ou un
    net non nul non-USDT (= trade en cours). Best-effort, liste triée par emprunt."""
    out = []
    for row in _signed_get(path):
        coin = str(row.get("coin") or "").upper()
        borrow = _num(row.get("borrow"))
        net = _num(row.get("net"))
        interest = _num(row.get("interest"))
        total = _num(row.get("totalAmount"))
        # trade en cours = emprunt actif (levier) OU exposition nette non triviale hors USDT
        if borrow <= 0 and (coin in ("USDT", "USDC") or abs(net) < 1e-8):
            continue
        entry = {"coin": coin, "net": round(net, 8), "borrow": round(borrow, 8),
                 "interest": round(interest, 8), "total": round(total, 8)}
        if key_field == "symbol":
            entry["symbol"] = row.get("symbol")
        out.append(entry)
    out.sort(key=lambda r: -r["borrow"])
    return out


def margin_isolated():
    """Marge ISOLÉE par symbole (emprunt actif)."""
    return _margin_rows("/api/v2/margin/isolated/account/assets", "symbol")


def margin_crossed():
    """Marge CROISÉE par coin (emprunt actif)."""
    return _margin_rows("/api/v2/margin/crossed/account/assets", "coin")


def futures():
    """Positions perp USDT-M ouvertes (taille > 0). Sens, entrée, PnL latent, levier,
    mode de marge (isolated/crossed)."""
    rows = _signed_get("/api/v2/mix/position/all-position",
                       {"productType": "USDT-FUTURES", "marginCoin": "USDT"})
    out = []
    for row in rows:
        size = _num(row.get("total"))
        if size <= 0:
            continue
        entry = _num(row.get("openPriceAvg") or row.get("averageOpenPrice"))
        mark = _num(row.get("markPrice"))
        out.append({
            "symbol": row.get("symbol"),
            "side": str(row.get("holdSide") or "").upper(),         # LONG / SHORT
            "size": round(size, 8),
            "entry": round(entry, 6) if entry else None,
            "mark": round(mark, 6) if mark else None,
            "leverage": _num(row.get("leverage")),
            "margin_mode": str(row.get("marginMode") or "").lower(),  # isolated / crossed
            "margin_usdt": round(_num(row.get("marginSize") or row.get("margin")), 4),
            "upnl_usdt": round(_num(row.get("unrealizedPL")), 4),
            "notional_usdt": round(size * (mark or entry or 0), 2),
        })
    out.sort(key=lambda r: -abs(r["upnl_usdt"]))
    return out


def parse_all_account_balance(rows):
    """Parse la ventilation officielle par type de compte (PUR, testable) :
    [{accountType, usdtBalance}] -> {"accounts": {type: usdt}, "total_usdt": somme}."""
    accounts = {}
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        at = str(row.get("accountType") or "").lower()
        if at:
            accounts[at] = round(_num(row.get("usdtBalance")), 2)
    return {"accounts": accounts, "total_usdt": round(sum(accounts.values()), 2)}


def all_account_balance():
    """Portefeuille TOTAL (tous les comptes : spot/futures/earn/bots/marge/funding)
    via l'endpoint officiel de consultation. LECTURE SEULE, 1 GET signé."""
    return parse_all_account_balance(_signed_get("/api/v2/account/all-account-balance"))


def snapshot():
    """Agrège les 4 catégories. Chaque bloc est best-effort ([] si erreur/vide) : le
    dashboard affiche ce qui est disponible sans jamais casser. LECTURE SEULE."""
    prices = _prices()
    out = {"spot": [], "margin_iso": [], "margin_cross": [], "futures": [], "errors": []}
    for name, fn in (("spot", lambda: spot(prices)), ("margin_iso", margin_isolated),
                     ("margin_cross", margin_crossed), ("futures", futures)):
        try:
            out[name] = fn()
        except Exception as exc:                    # noqa: BLE001 — best-effort par catégorie
            out["errors"].append(f"{name}: {type(exc).__name__}")
    out["counts"] = {k: len(out[k]) for k in ("spot", "margin_iso", "margin_cross", "futures")}
    out["totals"] = {
        "spot_usdt": round(sum((r["value_usdt"] or 0) for r in out["spot"]), 2),
        "futures_upnl_usdt": round(sum(r["upnl_usdt"] for r in out["futures"]), 4),
        "futures_notional_usdt": round(sum(r["notional_usdt"] for r in out["futures"]), 2),
    }
    return out


def main():
    import json
    snap = snapshot()
    print("=== POSITIONS RÉELLES EN COURS (lecture seule) ===")
    print(f"spot {snap['counts']['spot']} · marge iso {snap['counts']['margin_iso']} · "
          f"marge cross {snap['counts']['margin_cross']} · futures {snap['counts']['futures']}")
    print(json.dumps(snap, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
