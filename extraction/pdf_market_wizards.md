---
source: package/THE MARKET WIZARDS.pdf
category: canon
action: extracted
target: docs/RESEARCH_NOTES.md (§ « Invariants des traders gagnants »)
---

## Leçon canonique à extraire
Interviews de top traders (Schwager) — les **invariants** récurrents :
- **risque par trade < 1-2 %** du capital.
- **edge clairement défini** + **patience** pour n'agir que quand l'edge est présent.
- **stops non-négociables** ; **scaling** rationnel hors-émotion.
- **journaliser** chaque décision et la revoir froidement.
- **diversifier le risque, pas le bruit** (peu de paris, mais bien choisis).

## Cible d'intégration
- `docs/RESEARCH_NOTES.md` — § court avec ces invariants comme **règles dures**
  du moteur risque.
- `risk_manager.py` / `risk_limits.py` — vérifier que les seuils par défaut
  respectent ces invariants (≤2 %/trade, drawdown cap, max positions).
