---
source: package/Trading in the Zone - Mark Douglas.pdf (+ `…(2001) A202.pdf` dans PDF/)
category: canon
action: extracted
target: docs/RESEARCH_NOTES.md, agents (préambule système des agents-décideurs)
---

## Leçon canonique à extraire (résumé exploitable)
- **Penser en probabilités**, pas en certitudes : chaque trade est un échantillon
  d'une distribution. Edge = écart positif sur N trades, pas sur 1.
- **Cinq vérités fondamentales** : n'importe quoi peut arriver ; tu n'as pas
  besoin de savoir ce qui va arriver pour gagner ; il y a une distribution
  aléatoire entre gains et pertes pour toute série ; un edge n'est qu'une probabilité ;
  chaque instant de marché est unique.
- **Discipline mécanique** : suivre le système, pas l'émotion ; les overrides
  manuels détruisent l'attente mathématique.

## Cible d'intégration
- `docs/RESEARCH_NOTES.md` — § « Cadre mental opérationnel » : règles dérivées
  (no-override sur signal validé, journaliser chaque overruling, mesurer le coût).
- préambule système des agents décideurs (`preorder_approval.py`, `agent_control.py`) :
  rejet de toute « urgence » humaine qui contredit un signal sans nouvelle donnée.
