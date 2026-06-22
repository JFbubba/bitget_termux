"""
order_flow.py — microstructure (CVD, carnet d'ordres, niveaux de liquidation).

Classement : SAFE (calcul pur, aucune I/O, aucun ordre, aucun secret).

Couvre les points "pro" : CBOT / carnet d'ordres, Tape (Time & Sales) et
zones de liquidation — uniquement la COUCHE DE CALCUL, alimentée par des
données déjà récupérées (trades / order book / OI) en lecture seule.

  - cumulative_volume_delta : agressivité acheteur vs vendeur (depuis la "tape")
  - order_book_imbalance    : déséquilibre du carnet (profondeur)
  - liquidation_levels      : prix de liquidation approx. par levier (clusters)

Le fetch réel (API Bitget depth/trades, MCP CoinDesk) sera une couche fine
distincte ; ces fonctions restent testables sans réseau.
"""


def _level_size(level):
    """Taille d'un niveau de carnet : [price, size] ou {"size"/"qty": ...}."""
    if isinstance(level, dict):
        return float(level.get("size", level.get("qty", 0.0)))
    return float(level[1])


def cumulative_volume_delta(trades):
    """CVD : volume acheteur agressif - volume vendeur agressif (depuis la tape).

    `trades` : liste de {"side": "buy"/"sell", "size": x} (alias qty/amount).
    Retourne {cvd, series, buy_volume, sell_volume}. CVD > 0 = pression acheteuse.
    """
    if not trades:
        raise ValueError("cumulative_volume_delta: aucune transaction fournie")
    series, cvd, buy_v, sell_v = [], 0.0, 0.0, 0.0
    for trade in trades:
        size = float(trade.get("size", trade.get("qty", trade.get("amount", 0.0))))
        side = str(trade.get("side", "")).lower()
        if side in ("buy", "b", "bid", "long"):
            cvd += size
            buy_v += size
        elif side in ("sell", "s", "ask", "short"):
            cvd -= size
            sell_v += size
        series.append(cvd)
    return {"cvd": cvd, "series": series, "buy_volume": buy_v, "sell_volume": sell_v}


def order_book_imbalance(bids, asks, depth=None):
    """Déséquilibre du carnet sur les `depth` premiers niveaux.

    `bids`/`asks` : listes de [price, size] ou {"price","size"}.
    Retourne {imbalance, bid_volume, ask_volume} ; imbalance dans [-1, 1]
    (> 0 = pression acheteuse / mur d'achat).
    """
    if not bids or not asks:
        raise ValueError("order_book_imbalance: carnet vide")
    top_bids = bids[:depth] if depth else bids
    top_asks = asks[:depth] if depth else asks
    bid_vol = sum(_level_size(x) for x in top_bids)
    ask_vol = sum(_level_size(x) for x in top_asks)
    total = bid_vol + ask_vol
    imbalance = (bid_vol - ask_vol) / total if total else 0.0
    return {"imbalance": imbalance, "bid_volume": bid_vol, "ask_volume": ask_vol}


def liquidation_levels(entry_price, leverages, side="long", maintenance_margin=0.005):
    """Prix de liquidation APPROCHÉS par levier (zones de liquidation).

    Approximation : mouvement de liquidation ≈ (1/levier) - marge_maintenance.
      long  -> prix = entry * (1 - move)
      short -> prix = entry * (1 + move)
    NB : approximation (ignore frais, isolated/cross, paliers exacts). Sert à
    repérer des CLUSTERS de liquidation autour des leviers usuels (5/10/25/50/100x).
    Retourne une liste triée [{leverage, price}]. Calcul pur, aucun ordre.
    """
    if entry_price <= 0:
        raise ValueError("liquidation_levels: entry_price doit être > 0")
    side = str(side).lower()
    out = []
    for lev in leverages:
        if lev <= 0:
            continue
        move = (1.0 / lev) - maintenance_margin
        if side in ("long", "buy"):
            price = entry_price * (1 - move)
        else:
            price = entry_price * (1 + move)
        out.append({"leverage": lev, "price": price})
    if not out:
        raise ValueError("liquidation_levels: aucun levier valide")
    out.sort(key=lambda x: x["price"])
    return out


def main():
    print("=== ORDER FLOW (lecture seule) ===")
    print("Couche de calcul microstructure : CVD, déséquilibre carnet, liquidations.")
    print("Alimentée par trades/order book/OI déjà récupérés. Voir docs/PRO_INDICATORS.md.")
    print("VERDICT: SAFE — aucun ordre, aucun secret.")


if __name__ == "__main__":
    main()
