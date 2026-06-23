---
source: package/Technique_DexScreener_GMGN.docx
category: crypto-onchain
action: extracted
target: assistant/tools.py (futur wrapper DexScreener / GMGN, si on ouvre volet DEX)
---

## Sujet
Technique de scan **DexScreener + GMGN** pour repérer des tokens DEX émergents.

## Valeur extraite
- Filtres clés : âge token, liquidity locked, holders top10 %, volume/liq ratio.
- Cross-check **GMGN** : score wallet creator, distribution snipers.
- Pratique très **niche** et risquée — sortie de portefeuille typique très négative.

## Cible d'intégration
- Hors scope crypto-futures Bitget actuel.
- Si volet DEX un jour : `assistant/tools.py` → wrappers DexScreener/GMGN read-only.
