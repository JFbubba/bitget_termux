---
source: package/Candlestick Pattern Cheat Sheet.pdf
category: method
action: extracted
target: order_signal_engine.py (détecteur patterns), docs/RESEARCH_NOTES.md
---

## Sujet
Cheat-sheet des patterns chandeliers (hammer, engulfing, harami, doji,
morning/evening star, three white soldiers / black crows, etc.).

## Valeur extraite
- **liste exhaustive** + règles de formation simples → facile à coder en détecteur.
- **important** : un pattern seul n'a pas d'edge ; il faut un **contexte**
  (niveau VP, divergence RSI, sweep, etc.). À utiliser comme **confirmateur**, pas
  comme déclencheur unique.

## Cible d'intégration
- `order_signal_engine.py` — détecteur `candlestick_patterns(ohlc)` retournant la
  liste des patterns détectés à la dernière bougie.
- `swarm_brain.py` — pondération **faible** par défaut (gate par contexte).
- `docs/RESEARCH_NOTES.md` — § court : « les patterns chandeliers sont des
  confirmateurs, pas des signaux ».
