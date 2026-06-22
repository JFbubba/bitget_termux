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


def _news(currencies=None, filter=None, **_):
    import news_feed
    return news_feed.fetch_news(currencies=currencies, filter_=filter)


def _prices(coins="BTC", **_):
    import coingecko_data
    toks = [c.strip() for c in str(coins).replace(" ", ",").split(",") if c.strip()]
    return coingecko_data.fetch_markets(toks or ["BTC"])


def _market_overview(**_):
    import coingecko_data
    return coingecko_data.fetch_global()


def _aggregated_derivs(symbol="BTCUSDT", **_):
    import aggregated_derivs
    return aggregated_derivs.fetch_aggregate(str(symbol).upper())


def _prediction_markets(query=None, **_):
    import polymarket_data
    return polymarket_data.fetch_markets(query)


def _brain(symbol="BTCUSDT", **_):
    import swarm_brain
    return swarm_brain.read(str(symbol).upper())


def _liquidations(symbol="BTCUSDT", **_):
    import liquidations
    return liquidations.fetch_liquidations(str(symbol).upper())


def _economic_calendar(currencies=None, impact="High", **_):
    import econ_calendar
    curr = None
    if currencies:
        curr = [c.strip().upper() for c in str(currencies).replace(" ", ",").split(",") if c.strip()]
    return econ_calendar.fetch_calendar(impact_min=impact or "High", currencies=curr)


def _arbitrage(symbol="BTCUSDT", **_):
    import arbitrage
    return arbitrage.detect(str(symbol).upper())


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
    "get_news": _news,
    "get_prices": _prices,
    "get_market_overview": _market_overview,
    "get_aggregated_derivs": _aggregated_derivs,
    "get_prediction_markets": _prediction_markets,
    "get_brain_read": _brain,
    "get_liquidations": _liquidations,
    "get_economic_calendar": _economic_calendar,
    "get_arbitrage": _arbitrage,
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
    {
        "name": "get_news",
        "description": "Dernières news crypto (CryptoPanic). Optionnel : filtrer par devises et par sentiment.",
        "input_schema": {"type": "object", "properties": {"currencies": {"type": "string", "description": "ex. BTC,ETH (optionnel)"}, "filter": {"type": "string", "enum": ["hot", "rising", "bullish", "bearish", "important"]}}},
    },
    {
        "name": "get_prices",
        "description": "Prix, variation 24h, market cap et volume (CoinGecko) pour un ou plusieurs actifs.",
        "input_schema": {"type": "object", "properties": {"coins": {"type": "string", "description": "symboles séparés par des virgules, ex. BTC,ETH,SOL"}}, "required": ["coins"]},
    },
    {
        "name": "get_market_overview",
        "description": "Vue d'ensemble du marché crypto (CoinGecko) : market cap totale, dominance BTC, variation 24h.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "get_aggregated_derivs",
        "description": "Funding & open interest AGRÉGÉS multi-exchange (Binance+Bybit+Bitget) : OI total en USD et funding 8h pondéré par l'OI. Pour jauger le positionnement des dérivés.",
        "input_schema": {"type": "object", "properties": {"symbol": {"type": "string", "description": "ex. BTCUSDT, ETHUSDT"}}, "required": ["symbol"]},
    },
    {
        "name": "get_prediction_markets",
        "description": "Cotes des marchés de prédiction Polymarket (probabilités implicites) — sentiment sur des événements (Fed, BTC, élections...). Lecture seule. Optionnel : un mot-clé de recherche.",
        "input_schema": {"type": "object", "properties": {"query": {"type": "string", "description": "ex. bitcoin, fed, election (optionnel)"}}},
    },
    {
        "name": "get_brain_read",
        "description": "CERVEAU (essaim d'agents) : agrège 6 agents spécialisés (order-flow, technique, macro, sentiment, dérivés, liquidations) en un consensus pondéré → biais LONG/SHORT/NEUTRE + conviction. Les poids s'apprennent (auto-évaluation des décisions passées vs prix réalisé). Aide à la décision adaptative, lecture seule.",
        "input_schema": {"type": "object", "properties": {"symbol": {"type": "string", "description": "ex. BTCUSDT, ETHUSDT, SOLUSDT"}}, "required": ["symbol"]},
    },
    {
        "name": "get_liquidations",
        "description": "Carte de liquidations (clusters/heatmap) : estime les pools de liquidations au-dessus/en dessous du prix à partir du prix et de l'open interest réel multi-exchange. 'net' > 0 = aimant haussier (pools de shorts au-dessus). MODÈLE estimatif (prix×levier×OI), pas un flux exchange. Lecture seule.",
        "input_schema": {"type": "object", "properties": {"symbol": {"type": "string", "description": "ex. BTCUSDT, ETHUSDT"}}, "required": ["symbol"]},
    },
    {
        "name": "get_economic_calendar",
        "description": "Calendrier économique de la semaine (Forex Factory) : événements macro à fort impact (FOMC, CPI, NFP, PCE...) avec heures restantes, prévision et valeur précédente. Sert à repérer les fenêtres de volatilité / éviter de se positionner juste avant. Lecture seule.",
        "input_schema": {"type": "object", "properties": {"currencies": {"type": "string", "description": "filtre devises séparées par virgule, ex. USD,EUR (optionnel)"}, "impact": {"type": "string", "enum": ["High", "Medium", "Low"], "description": "impact minimum (défaut High)"}}},
    },
    {
        "name": "get_arbitrage",
        "description": "DÉTECTION d'écarts de prix (lecture seule, aucune exécution) : spread spot inter-exchange (Binance/Bybit/OKX/Bitget), base perp↔spot, spread de funding. Écarts BRUTS hors frais/slippage/retrait. Veille uniquement.",
        "input_schema": {"type": "object", "properties": {"symbol": {"type": "string", "description": "ex. BTCUSDT, ETHUSDT"}}, "required": ["symbol"]},
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
