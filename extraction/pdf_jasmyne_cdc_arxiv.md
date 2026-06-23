---
source: package/Aladdin - Jasmyne/jasmyne_cahier_des_charges_style_arxiv.pdf
category: agent-architecture
action: extracted
target: docs/RESEARCH_NOTES.md (§ « Vision Crypto-Aladdin perso »)
---

## Sujet
Cahier des charges (style arXiv) d'un « Crypto-Aladdin personnel » pour le
projet Jasmyne — vision du système de référence visé.

## Valeur extraite
- **Cibles fonctionnelles** (analyse risque portefeuille, scoring, monitoring,
  alertes, exécution paper d'abord puis live).
- **Architecture multi-modules** : on retrouve la même partition que notre repo
  (agents, brain, risk, dashboard, paper trading).
- Validation : notre architecture actuelle **converge** déjà avec ce cahier.
  Sert de checklist pour ne pas oublier de capacités (ex. stress-test régime,
  what-if scenarios).

## Cible d'intégration
- `docs/RESEARCH_NOTES.md` — § « Vision Crypto-Aladdin perso » avec la checklist
  fonctionnelle à cocher au fil des releases.
- À croiser avec `folder_aladdin_jasmyne.md` (le dossier complet contient docx,
  xlsx, pptx du même chantier).
