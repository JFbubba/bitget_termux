---
source: package/strategie_trading_agressivite_3_sur_5.docx (+ `-1.docx` doublon)
       (+ `Aladdin - Jasmyne/strategie_trading_aladdin_style_agressivite_3_sur_5*.docx`)
category: strategy-doc
action: extracted
target: docs/RESEARCH_NOTES.md (§ « Profils d'agressivité »), config_guard_agent.py
---

## Sujet
Stratégie cible avec un **niveau d'agressivité 3/5** (modérée) — sizing, fréquence,
type de signaux acceptés.

## Valeur extraite
- Concept de **profil d'agressivité** (1 à 5) pilotant : taille position max,
  nombre trades/jour, RR min, distance stop, levier autorisé.
- Profil 3/5 = compromis sain (≤ 2 %/trade, RR ≥ 1.5, levier ≤ 5x).

## Cible d'intégration
- `config_guard_agent.py` — exposer un paramètre `aggressiveness ∈ {1..5}` qui
  contraint les autres params (au lieu de tous les régler à la main).
- `docs/RESEARCH_NOTES.md` — § « Profils d'agressivité » avec la grille
  (1→5) → (sizing, RR, levier, fréquence).
