---
source: package/L'alchimie de la finance - Soros.pdf (+ `L'alchimie de la finance PDF.pdf` dans PDF/)
category: canon
action: extracted
target: docs/RESEARCH_NOTES.md (§ « Réflexivité »), macro_context.py
---

## Leçon canonique
- **Réflexivité** : les participants modifient ce qu'ils observent → les fondamentaux
  ne sont pas exogènes, ils sont influencés par l'opinion sur eux-mêmes.
- **Boom-bust** : une narrative auto-renforçante crée une bulle, jusqu'au
  retournement (twilight zone).
- en pratique : surveiller les **divergences narrative / réalité** (sentiment qui
  ignore une dégradation, ou inversement).

## Cible d'intégration
- `macro_context.py` — feature `sentiment_vs_realized` (ex. fear&greed vs vol
  réalisée 30j, ou flux ETF vs prix on-chain).
- `docs/RESEARCH_NOTES.md` — § « Réflexivité » : pourquoi le sentiment doit être
  croisé avec une mesure dure (réalisé) plutôt que pris isolément.
