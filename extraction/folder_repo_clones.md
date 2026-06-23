---
source: package/{ccxt, freqtrade, openbb-terminal, hummingbot, Glassnode/glassnode-api-python-client, goat, OctoBot, OctoBot-Trading, OpenBB, AI-Trader/, trading-frameworks/{OpenBB, TradingAgents}, …}
       + tous les fichiers `*.git-*` à la racine de `package/`
category: repo-clone
action: skipped
target: —
---

## Contenu
- **Frameworks crypto trading OSS clonés** :
  - `ccxt/` (~29 Mo) — librairie exchange (déjà en pip dep).
  - `freqtrade/` — bot Python (clone partiel).
  - `openbb-terminal/`, `OpenBB.git-*` — terminal quant.
  - `hummingbot/` — market-maker DEX.
  - `OctoBot/`, `OctoBot.git-*`, `OctoBot-Trading.git-*` — bot Python crypto.
  - `goat/` — agentic framework on-chain.
  - `Glassnode/glassnode-api-python-client/` — wrapper officiel.
  - `TradingAgents.git-*` + `TradingAgents/` — voir `folder_tradingagents.md`.
- **Git metadata éclatés** : `*.git-HEAD`, `*.git-config`, `*.git-index`,
  `*.git-logs-*`, `*.git-packed-refs`, `*.git-refs-*`, `*.git-shallow`.

## Pourquoi skip
- Code public, déjà à jour upstream → cloner via `pip install` / `git clone` au
  besoin, ne **pas** importer du code dans le repo.
- Les fichiers `.git-*` éclatés viennent probablement d'un export raté de
  `.git/` dans le Drive (Drive Desktop ne gère pas les dotfiles → ils ressortent
  préfixés). Inutiles tels quels, polluent l'arborescence.

## Cible d'intégration
- Aucune.
- Suggestion (hors scope cette passe) : déplacer tous ces clones et `*.git-*`
  dans `package/_oss_clones/` côté Drive pour faire le tri visuel, ou les
  supprimer du Drive si déjà publics ailleurs.
