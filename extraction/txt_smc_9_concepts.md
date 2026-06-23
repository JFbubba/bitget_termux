---
source: package/702646104-9-Smart-Money-Concepts-that-Every-Trader-Must-Know.txt
category: method
action: extracted
target: docs/RESEARCH_NOTES.md (§ SMC consolidé avec pdf_ict_breaker_block.md)
---

## Sujet
Liste « 9 SMC concepts » — order block, fair value gap, breaker, mitigation block,
liquidity pool, BOS/CHoCH, premium/discount, optimal trade entry, market structure.

## Valeur extraite
- **glossaire normalisé** : nom canonique de chaque concept, à reprendre dans le
  code (slugs identiques entre features et logs).
- **BOS vs CHoCH** : distinction utile (continuation vs reversal de structure).
- **premium/discount** : zone supérieure / inférieure d'un range — règle directionnelle
  simple (vendre en premium, acheter en discount, si trend confirmé).

## Cible d'intégration
- fusionner dans `docs/RESEARCH_NOTES.md` avec la fiche ICT breaker — un seul § SMC
  unifié, focus sur ce qui est mécanisable (BOS/CHoCH, OB, FVG, breaker).
- alimenter `order_signal_engine.py` avec un détecteur de structure (HH/HL/LH/LL).
