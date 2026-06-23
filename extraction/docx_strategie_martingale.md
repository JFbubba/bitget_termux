---
source: package/Stratégie _ Martingale.docx (+ `Markdown/Stratégie _ Martingale.md`)
category: strategy-doc
action: extracted
target: risk_manager.py / risk_limits.py (interdire), docs/RESEARCH_NOTES.md
---

## Sujet
Stratégie **martingale** : doubler la mise après chaque perte pour récupérer.

## Valeur extraite (négative — c'est une anti-référence)
- Mathématiquement : edge attendu **négatif** pour tout capital fini ; converge
  vers la ruine en présence de tail risk (et le marché en a).
- **Aucune** variante ("anti-martingale", "demi-martingale", "Kelly inversée
  bricolée") ne sauve un système sans edge réel.

## Cible d'intégration
- `risk_limits.py` / `risk_manager.py` — règle dure : **interdire** toute
  augmentation de taille après perte sans **nouveau signal indépendant**. Test à
  écrire (le rejet doit être visible dans le journal).
- `docs/RESEARCH_NOTES.md` — § court « Pourquoi la martingale est bannie »
  (avec lien vers cette fiche).
