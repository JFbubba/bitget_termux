"""
fair_price.py — prix de référence CROSS-EXCHANGE (médiane) + premium Bitget.

Classement : SAFE. Lecture seule, AUCUN ordre. Sert « accumuler au MEILLEUR prix » :
compare le prix Bitget à la médiane de plusieurs exchanges (Binance, Bybit, OKX) pour
savoir si Bitget cote en PREMIUM (on paierait trop cher) ou en DISCOUNT (bonne affaire).
Réutilise les fetchers keyless de `arbitrage.py` -> aucune nouvelle dépendance.

Idée reprise de l'écosystème CCXT (agrégation multi-exchange) mais SANS la lib lourde :
on ne tire que ce qui sert, avec nos requêtes existantes.
"""


def median(xs):
    """Médiane pure (None si vide)."""
    v = sorted(float(x) for x in xs if x is not None and float(x) > 0)
    if not v:
        return None
    n = len(v)
    return v[n // 2] if n % 2 else (v[n // 2 - 1] + v[n // 2]) / 2.0


def premium_pct(price, reference):
    """Premium/discount de `price` vs `reference`, en %. PUR. >0 = price au-dessus."""
    if not price or not reference:
        return None
    return round((float(price) - float(reference)) / float(reference) * 100.0, 4)


def is_fair_to_buy(premium, max_premium_pct=0.30):
    """Bon moment pour ACHETER sur Bitget ? (pas en premium excessif vs marché). PUR.
    premium None (inconnu) -> True : on ne bloque jamais un achat faute de données."""
    if premium is None:
        return True
    return float(premium) <= float(max_premium_pct)


def fair_value(symbol="BTCUSDT", exclude=("bitget",)):
    """Référence = MÉDIANE des exchanges (hors Bitget par défaut, pour un repère
    indépendant). Best-effort, ne lève jamais. Réutilise arbitrage.SPOT_FUNCS."""
    try:
        import arbitrage as ab
        quotes = {ex: ab._safe(fn, symbol.upper()) for ex, fn in ab.SPOT_FUNCS.items()}
    except Exception:
        quotes = {}
    bitget = quotes.get("bitget")
    ref = [v for ex, v in quotes.items() if ex not in exclude and v]
    fair = median(ref)
    return {"fair": round(fair, 2) if fair else None, "n": len(ref),
            "sources": {k: round(v, 2) for k, v in quotes.items() if v},
            "bitget": round(bitget, 2) if bitget else None,
            "premium_pct": premium_pct(bitget, fair)}


def build_report(symbol="BTCUSDT"):
    fv = fair_value(symbol)
    p = fv.get("premium_pct")
    tag = "n/a" if p is None else ("PREMIUM (cher)" if p > 0.3 else "DISCOUNT (bon)" if p < -0.3 else "aligné")
    return ("=== PRIX DE RÉFÉRENCE CROSS-EXCHANGE ===\n"
            f"Médiane (hors Bitget) : {fv.get('fair')} ({fv.get('n')} sources)\n"
            f"Bitget : {fv.get('bitget')} · premium {p}% -> {tag}\n"
            f"Sources : {fv.get('sources')}\n"
            "Lecture seule, aucun ordre. VERDICT: SAFE")


def main():
    import sys
    print(build_report(sys.argv[1] if len(sys.argv) > 1 else "BTCUSDT"))


if __name__ == "__main__":
    main()
