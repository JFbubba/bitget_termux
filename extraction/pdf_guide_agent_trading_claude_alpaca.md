---
source: package/Guide_Agent_Trading_Claude_Alpaca.pdf
category: agent-architecture
action: extracted
target: assistant/agent.py, assistant/tools.py
---

## Sujet
Guide pas-à-pas : agent trading avec **Claude + Alpaca** (broker US equities).

## Valeur extraite
- Patron d'**outils** (tool definitions) pour LLM de trading : `get_quote`,
  `get_positions`, `place_order`, `cancel_order`, `get_history`.
- Boucle agent : observation → décision → tool call → observation → ... (ReAct).
- Le broker (Alpaca) n'est pas le nôtre, mais l'**architecture des tools** est
  directement réutilisable pour Bitget.

## Cible d'intégration
- `assistant/agent.py` — vérifier qu'on a la même surface d'outils (`get_*`, `place_*`,
  `cancel_*`) mappée sur Bitget paper.
- `assistant/tools.py` — comparer la **granularité** des outils (rester read-only
  par défaut, write derrière un flag explicite).
