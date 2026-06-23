---
source: package/Choisir un canal Telegram de trading.docx (+ `Markdown/Choisir un canal Telegram de trading.md`)
category: crypto-onchain
action: extracted
target: docs/RESEARCH_NOTES.md (§ « Évaluer un signal externe »)
---

## Sujet
Critères pour **évaluer un canal Telegram** de signaux (qualité, transparence,
historique vérifiable).

## Valeur extraite (critères opérationnels)
- Track-record **horodaté** (chaque signal daté avant outcome).
- Mention systématique entry/SL/TP (sinon pas de RR mesurable).
- Pas de **survivor bias** dans les "captures" (montrer aussi les perdants).
- Taille d'échantillon (≥ 100 signaux) avant de juger.

## Cible d'intégration
- `docs/RESEARCH_NOTES.md` — § « Évaluer un signal externe » avec cette checklist.
- À appliquer au module `telegram_signal_listener` (cf. fiche
  `pdf_guide_signaux_telegram.md`) pour décider quels canaux on log.
