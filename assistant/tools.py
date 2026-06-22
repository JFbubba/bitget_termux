"""
assistant/tools.py — outils LECTURE SEULE exposés au LLM.

Classement : SAFE. Chaque outil n'appelle qu'une fonction de DONNÉES en lecture
seule (order-flow, macro, confluence, détection rug, DeFi, DEX, sentiment,
stats). AUCUN outil ne peut passer/annuler un ordre ni modifier quoi que ce soit.
Les imports sont paresseux et les erreurs renvoyées proprement au LLM.
"""

import json


def _order_flow(symbol="BTCUSDT", **_):
    import bitget_market_data
    return bitget_market_data.market_snapshot(str(symbol).upper())


def _macro(**_):
    import macro_context
    return macro_context.macro_snapshot()


def _confluence(symbol="BTCUSDT", side="LONG", **_):
    import confluence_score
    return confluence_score.assess(str(symbol).upper(), str(side).upper())


def _token_safety(address, chain="eth", **_):
    import token_safety
    return token_safety.check_token(address, chain)


def _defi(**_):
    import defi_data
    return defi_data.fetch_chains(top=6)


def _dex(query, **_):
    import dex_scanner
    return dex_scanner.fetch_search(query, top=8)


def _fear_greed(**_):
    import sentiment_index
    return sentiment_index.fetch_fear_greed()


def _trade_stats(**_):
    import stats_report
    return stats_report.compute_stats(stats_report.load_rows())


def _technicals(symbol="BTCUSDT", granularity="15m", **_):
    import technicals
    return technicals.technicals(str(symbol).upper(), str(granularity))


def _liquidity(symbol="BTCUSDT", **_):
    import technicals
    return technicals.book_liquidity(str(symbol).upper())


TOOL_FUNCS = {
    "get_order_flow": _order_flow,
    "get_macro": _macro,
    "get_confluence": _confluence,
    "check_token_safety": _token_safety,
    "get_defi_overview": _defi,
    "search_dex": _dex,
    "get_fear_greed": _fear_greed,
    "get_trade_stats": _trade_stats,
    "get_technicals": _technicals,
    "get_liquidity_clusters": _liquidity,
}

TOOLS = [
    {
        "name": "get_order_flow",
        "description": "Order-flow Bitget d'un symbole : prix mid, déséquilibre du carnet, CVD (Cumulative Volume Delta = pression acheteur-vendeur cumulée), open interest, funding. Pour analyser la microstructure.",
        "input_schema": {"type": "object", "properties": {"symbol": {"type": "string", "description": "ex. BTCUSDT, ETHUSDT, SOLUSDT"}}, "required": ["symbol"]},
    },
    {
        "name": "get_technicals",
        "description": "Indicateurs techniques sur bougies : VWAP, Volume SMA, Volume Profile (POC/VAH/VAL ~ VPVR), TPO (profil temps-prix), RSI14, ATR14, EMA20/50, biais volume.",
        "input_schema": {"type": "object", "properties": {"symbol": {"type": "string"}, "granularity": {"type": "string", "description": "1m|5m|15m|1H|4H|1D (défaut 15m)"}}, "required": ["symbol"]},
    },
    {
        "name": "get_liquidity_clusters",
        "description": "Murs de liquidité du carnet (~ order-book heatmap statique) : plus grosses tailles côté bid et ask.",
        "input_schema": {"type": "object", "properties": {"symbol": {"type": "string"}}, "required": ["symbol"]},
    },
    {
        "name": "get_macro",
        "description": "Contexte macro / régime de risque (VIX, courbe 2s10s, DXY, pétrole) via FRED.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "get_confluence",
        "description": "Confluence d'un signal LONG/SHORT avec la microstructure et la macro. Aide à la décision en lecture seule.",
        "input_schema": {"type": "object", "properties": {"symbol": {"type": "string"}, "side": {"type": "string", "enum": ["LONG", "SHORT"]}}, "required": ["symbol", "side"]},
    },
    {
        "name": "check_token_safety",
        "description": "DÉTECTION rug/honeypot d'un token (GoPlus+Honeypot.is en EVM, RugCheck en Solana). Sert à ÉVITER les tokens douteux.",
        "input_schema": {"type": "object", "properties": {"address": {"type": "string"}, "chain": {"type": "string", "description": "eth|bsc|base|polygon|arbitrum|solana"}}, "required": ["address"]},
    },
    {
        "name": "get_defi_overview",
        "description": "TVL DeFi totale + top chaînes (DefiLlama).",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "search_dex",
        "description": "Recherche de paires/tokens sur les DEX par liquidité (DexScreener).",
        "input_schema": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]},
    },
    {
        "name": "get_fear_greed",
        "description": "Indice Fear & Greed crypto (sentiment marché).",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "get_trade_stats",
        "description": "Statistiques des résultats finalisés (TP/SL, taux de réussite) du moteur paper.",
        "input_schema": {"type": "object", "properties": {}},
    },
]


def dispatch(name, args):
    """Exécute un outil read-only et retourne une chaîne (JSON compact, tronqué)."""
    func = TOOL_FUNCS.get(name)
    if func is None:
        return json.dumps({"error": f"outil inconnu: {name}"})
    try:
        result = func(**(args or {}))
        return json.dumps(result, ensure_ascii=False, default=str)[:6000]
    except Exception as exc:
        return json.dumps({"error": f"{type(exc).__name__}: {exc}"[:300]})
