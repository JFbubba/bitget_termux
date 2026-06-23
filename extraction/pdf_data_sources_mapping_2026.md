---
source: package/Mapping Key Financial and Crypto Actors 2026 — data sources.pdf
       (+ doublon dans `Aladdin - Jasmyne/Mapping and Analysis Framework…2026 A Structured Guide…pdf`)
category: crypto-onchain
action: extracted
target: assistant/tools.py (catalogue de sources), docs/RESEARCH_NOTES.md
---

## Sujet
Cartographie 2026 des **acteurs et sources de données** crypto+finance
(exchanges, on-chain analytics, terminaux, dashboards, dataroom).

## Valeur extraite
- Inventaire structuré (DeFi Llama, Dune, CryptoQuant, Glassnode, Token Terminal,
  Kaiko, Amberdata, etc.) → matière première pour un **catalogue de tools** LLM.
- Croise avec `md_source_acteurs_crypto.md` (liste manuscrite) et
  `md_outils_trading_liens.md` (liens).

## Cible d'intégration
- `assistant/tools.py` — ajouter des wrappers (read-only) pour les sources qu'on
  utilise déjà (CoinGecko, Bitget, peut-être Glassnode/CryptoQuant si abonnement).
- `docs/RESEARCH_NOTES.md` — § « Sources de vérité » : pour chaque famille de
  signal (orderflow, on-chain, dérivés, macro), quelle source on consulte en priorité.
