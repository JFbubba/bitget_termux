---
source: package/Discovery of a 13-Sharpe OOS Factor Drift.PDF
category: research
action: extracted
target: swarm_brain.py (up_fraction), risk_manager.py (kill-switch multi-trigger)
status_in_registry: traité
---

## Sujet
Note de recherche (référence arXiv 2511.12490) — un facteur de **drift de régime**
mesuré par la fraction de jours haussiers (`up_fraction`) sur une fenêtre. Le
résultat « 13-Sharpe » est suspect mais l'idée du gating régime est solide.

## Valeur extraite
- **feature** : `up_fraction` — proportion de barres / jours haussiers sur fenêtre
  N ; comme proxy ultra-simple de régime.
- **garde-fou** : **regime-gating** des stratégies (n'activer telle stratégie que
  si `up_fraction ∈ [a,b]`).
- **kill-switch multi-trigger** : combiner plusieurs déclencheurs (vol > seuil,
  drawdown > seuil, up_fraction sort de bande) pour arrêter le trading.

## Cible d'intégration
- `swarm_brain.py` ou `macro_context.py` — exposer `up_fraction` comme feature.
- `risk_manager.py` — implémenter le kill-switch multi-trigger (plusieurs
  conditions, n'importe laquelle suffit à couper).
- `docs/RESEARCH_NOTES.md` — § sur regime-gating et illustration du Sharpe suspect.
