---
source: package/Cahier des Charges Investing.com _ Analyse Détaill....docx
       (+ doublons `Aa dossi/Cahier des Charges…docx` et `PDF/Cahier des Charges…pdf`)
category: agent-architecture
action: extracted
target: docs/RESEARCH_NOTES.md (§ « Source secondaire — Investing.com »)
---

## Sujet
Cahier des charges pour intégrer **Investing.com** comme source d'analyse (news,
calendrier économique, sentiment analystes).

## Valeur extraite
- Inventaire des **données extractibles** d'Investing.com (calendrier macro, news,
  sentiment, idées analystes).
- Approche : scraping vs API non-officielle vs broker des données.
- **Risque légal/ToS** : scraping a souvent un coût juridique caché.

## Cible d'intégration
- `docs/RESEARCH_NOTES.md` — § court « Investing.com : utile pour calendrier
  macro, à éviter pour le sentiment (biaisé/notoire) ».
- Si on a besoin du calendrier macro, préférer une source à API propre
  (TradingEconomics, FRED, BLS) plutôt qu'Investing.
