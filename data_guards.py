"""data_guards.py — gardes de QUALITÉ des données (idées arbitrage-bot + Jasmine/data_quality).

Classement : SAFE (fonctions PURES, aucun réseau, aucun ordre). Rejette les données
corrompues AVANT qu'elles n'alimentent les agents / le sizing — un book croisé, une série
avec un saut absurde, une quote périmée sont des sources de faux signaux et de mauvais
prix. Fail-safe : en cas d'entrée illisible, on renvoie « invalide » (l'appelant dégrade)."""
from __future__ import annotations


def quote_valid(bid, ask):
    """PUR : book SAIN — bid>0, ask>0, ask>=bid. Rejette croisé/corrompu (idée arbitrage-bot)."""
    try:
        b, a = float(bid), float(ask)
    except (TypeError, ValueError):
        return False
    return b > 0 and a > 0 and a >= b


def quote_fresh(age_ms, max_age_ms=2500):
    """PUR : quote assez FRAÎCHE (age <= max). None/illisible -> False (fail-safe)."""
    try:
        return 0 <= float(age_ms) <= float(max_age_ms)
    except (TypeError, ValueError):
        return False


def series_ok(closes, min_len=2, max_jump_pct=80.0):
    """PUR : série de clôtures EXPLOITABLE ? assez de points, aucun None/NaN/<=0, et aucun
    saut d'une bougie à l'autre > max_jump_pct% (donnée corrompue / spike). (idée Jasmine)."""
    if not closes or len(closes) < int(min_len):
        return False
    prev = None
    for c in closes:
        try:
            f = float(c)
        except (TypeError, ValueError):
            return False
        if f != f or f <= 0:                       # NaN ou <= 0
            return False
        if prev and abs(f / prev - 1.0) * 100.0 > float(max_jump_pct):
            return False
        prev = f
    return True


def cap_by_liquidity(cap, price, size):
    """PUR : notionnel PLAFONNÉ par la liquidité affichée (top-of-book). size<=0 -> cap
    (jamais d'infini). (idée arbitrage-bot _max_notional_from_top_of_book)."""
    try:
        liq = float(price) * float(size)
        cap = float(cap)
    except (TypeError, ValueError):
        return None
    return min(cap, liq) if liq > 0 else cap
