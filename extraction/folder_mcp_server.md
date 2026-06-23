---
source: package/MCP Server/
category: mcp-server
action: extracted
target: assistant/tools.py ou nouveau dossier `mcp/` si on expose notre propre serveur
---

## Contenu (12 sous-dossiers)
- `alpaca-mcp-server/` — broker US equity (hors scope crypto-futures).
- `dexscreener-mcp-server/` — DEX (hors scope actuel).
- `kospi-kosdaq-stock-server/` — bourse coréenne (hors scope).
- `mcp-crypto-price/` — prix crypto (chevauche notre stack).
- `mcp-trader/` — trader générique.
- `trade-it-mcp/`, `tradingview-mcp/` — exécution / TradingView.
- `maverick-mcp/`, `masumi-mcp-server/`, `create-mcp-server/`,
  `mcp/`, `ansible/`.

## Valeur extraite
- Inventaire **utile** : tour d'horizon de ce qui existe en MCP côté trading.
- Pour le repo : on ne consomme pas (encore) ces MCP. Si un jour on en expose un
  **Bitget MCP** propre, regarder :
  - `create-mcp-server/` pour le scaffolding ;
  - `tradingview-mcp/` pour un exemple de serveur orienté charts.
- `mcp-crypto-price` ne sert pas (Bitget direct est plus précis pour nous).

## Cible d'intégration
- Pas d'import. Référence pour quand on construira notre **propre** MCP server.
- `docs/RESEARCH_NOTES.md` — § court « MCP server : on en consomme via Claude
  Desktop / Code, on n'en expose pas tant qu'il n'y a pas de besoin ».
