---
source: package/SOURCE d'informations - acteurs crypto.md
category: crypto-onchain
action: extracted
target: docs/RESEARCH_NOTES.md (§ « Acteurs & sources »), `assistant/tools.py`
---

## Sujet
**Liste brute** d'acteurs majeurs (DeFiLlama, Dune, Keyrock, Pendle, JPMorgan
Equity, Morpho, Yearn, Franklin Templeton, Vanguard, CryptoQuant, Arkham,
McKinsey, BlackRock, Kalshi, Polymarket, etc.) + propose une démarche
(classifier par spécialité, lister sites, construire un prompt d'agent).

## Valeur extraite
- Bonne **base de départ** pour le catalogue d'acteurs/sources du § "Sources de
  vérité" (cf. `pdf_data_sources_mapping_2026.md`).
- Beaucoup d'acteurs **hors-scope** crypto-futures (BBG terminal, Reuters terminal,
  Vanguard…) — à filtrer.

## Cible d'intégration
- Fusionner avec `pdf_data_sources_mapping_2026.md` dans un seul § "Acteurs &
  sources" de `docs/RESEARCH_NOTES.md`, avec tag par famille (DEX, on-chain,
  derivatives, macro, news).
- `assistant/tools.py` — n'ajouter des wrappers que pour les sources qu'on
  utilise vraiment (CoinGecko, Bitget, peut-être Glassnode/CryptoQuant si abo).
