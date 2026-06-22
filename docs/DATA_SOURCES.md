# DATA SOURCES & COVERAGE

Read-only data sourcing for the project. **No source here is used for order
execution or token creation/promotion** — analysis, detection, and signals only.

Key storage rule: keys live ONLY in `.env` (gitignored) or n8n credentials.
Never in chat, never committed. See `ENV_SETUP.md`.

## A. Built & validated live (keyless — nothing to configure)

| Source | Module | Use |
|---|---|---|
| Bitget public | `bitget_market_data.py` | prix, carnet, CVD, OI, funding (order-flow) |
| DefiLlama | `defi_data.py` | TVL DeFi + top chaînes |
| DexScreener | `dex_scanner.py` | recherche paires/tokens par liquidité |
| GoPlus Security | `token_safety.py` | sécurité token EVM (honeypot, taxes, owner…) |
| Honeypot.is | `token_safety.py` | simulation honeypot EVM |
| RugCheck | `token_safety.py` | rug report Solana (mint/freeze authority) |
| Fear & Greed (alternative.me) | `sentiment_index.py` | sentiment marché |
| FRED (CSV) | `macro_context.py` | DXY, VIX, courbe, pétrole |

## B. Pending keys (free tiers — wire once user adds keys to `.env`)

CoinGecko, CryptoPanic, FMP (macro+calendrier éco), Birdeye/Helius (Solana),
Neynar (Farcaster), X/Twitter (sentiment read-only), LunarCrush, Reddit,
Kalshi, Finnhub, AlphaVantage, TwelveData. Variable names already in `.env.example`.

## C. Available as MCP servers in the build session (no key needed here)

- **CoinDesk** (`mcp__CoinDesk__*`) — rich crypto: futures/spot/options OHLCV,
  OI, funding, orderbook metrics, on-chain DEX, news. Strong complement to Bitget.
- **Bigdata.com** — financial sentiment/news/company data.
- **prediction-mcp / Polymarket** — prediction-market odds (sentiment on events/BTC/Fed).

## D. User's `outils_trading.md` list — coverage verdict (32 links)

| # | Link (theme) | Status |
|---|---|---|
| 1 | investinglive.com (news macro) | ⏳ via CryptoPanic/FMP/news later |
| 2 | tradingeconomics.com (calendrier éco) | ⏳ FMP/Finnhub calendar (key) |
| 3 | tradingster.com (COT/options) | ⛔ niche, basse priorité |
| 4 | "sentinel macro analyst" (concept) | 💡 inspiration prompt macro |
| 5 | imprimantetrading.com | ❓ peu clair, à ignorer |
| 6 | TradingView "Unbiased Level Pro" (indicateur) | 💡 on calcule nos niveaux (confluence) |
| 7 | orallexa-ai-trading-agent (repo) | 💡 archi de référence |
| 8 | "phantom institutional flow / liquidation cluster" | 🟡 order-flow couvert ; liquidations = Coinglass (key) |
| 9 | Maestro-Trading-Bot (Solana sniper) | ⛔ HORS PÉRIMÈTRE (sniping) → détection only |
| 10 | Maestro-Sniper-Bot | ⛔ HORS PÉRIMÈTRE (sniping) |
| 11 | pump-fun-sniper-bot | ⛔ HORS PÉRIMÈTRE (pump.fun sniping) |
| 12 | ai-trade-agent (repo) | 💡 référence |
| 13 | crypto-arbitrage-bot | 🟡 futur : DÉTECTION d'arb (read-only), pas d'exécution |
| 14 | OpenInsider-MCP (insiders US) | ⏳ MCP self-host possible (actions US, basse prio) |
| 15 | sec-edgar-mcp (SEC filings) | ⏳ MCP self-host possible (actions US) |
| 16 | trade-prediction-markets (skill) | ✅ Polymarket via prediction-mcp |
| 17 | joinQuantish/skills | 💡 skills de référence |
| 18 | tradermonty/claude-trading-skills | 💡 skills de référence |
| 19 | claudemarketplaces finance | 💡 référence |
| 20 | crypto-market-research-agent | 💡 on construit l'équivalent |
| 21 | anthropic finance-agents (news) | 📄 contexte |
| 22 | claude financial-services | 📄 contexte |
| 23 | unusual-whales-mcp (options flow US) | ⏳ MCP (payant, actions) |
| 24 | Equibles (equities) | ⏳ actions, basse prio |
| 25 | congressmcp (trades du Congrès) | ⏳ MCP alt-data (basse prio) |
| 26 | shaanmajid/prediction-mcp | ✅ intégré (Polymarket) |
| 27 | Polymarket/agents | ✅ couvert |
| 28 | polymarket-trading-ai-model (skill) | ✅ couvert |
| 29 | Polymarket/agent-skills | ✅ couvert |
| 30 | Claude-Plugin-Marketplace-for-Polymarket | ✅ couvert |
| 31 | joinQuantish/skills (doublon) | 💡 référence |
| 32 | 666ghj/MiroFish | ✅ graphe relationnel repris (version simplifiée) sur le dashboard |

**Verdict** : le **cœur crypto est couvert** (Bitget + readers keyless + CoinDesk MCP +
Polymarket). Les **manques** sont surtout l'**alt-data actions US** (insiders, SEC,
Congrès, options-flow → liens 14/15/23/24/25, dispo en MCP, basse priorité pour du
crypto) et l'**arbitrage** (13, futur, en détection). Les bots **sniper/pump.fun**
(9/10/11) sont **volontairement hors périmètre** (pump-and-dump) → on fait de la
**détection** à la place via `token_safety.py`.
