---
source: package/L'investisseur intelligent - Graham.pdf (+ `Linvestisseur-…Benjamin.pdf` dans PDF/)
category: canon
action: extracted
target: docs/RESEARCH_NOTES.md (§ « Marge de sécurité »)
---

## Leçon canonique
- **Mr Market** : le marché est un partenaire bipolaire ; on ne lui obéit pas, on
  utilise ses excès.
- **Marge de sécurité** : prix d'entrée tel que même un scénario pessimiste reste
  acceptable — appliqué à la crypto, c'est un **buffer entre prix et stop**
  suffisant pour absorber le bruit normal du marché.
- **distinction investisseur / spéculateur** : assumer laquelle des deux casquettes
  on porte sur un trade donné.

## Cible d'intégration
- `docs/RESEARCH_NOTES.md` — § « Marge de sécurité » traduit en règle de sizing :
  distance au stop ≥ k×ATR, avec k dépendant du régime de volatilité.
- `position_sizer.py` — vérifier que la distance entrée→stop est calibrée sur ATR
  et pas sur un % fixe.
