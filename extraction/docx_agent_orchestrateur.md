---
source: package/Agent Orchestrateur_.docx (+ `Markdown/_Agent Orchestrateur .md`)
category: agent-architecture
action: extracted
target: agent_hub.py, agent_control.py, agent_loop.py
---

## Sujet
Concept d'**agent orchestrateur** central qui pilote la boucle de tous les autres
agents (collecte → analyse → décision → exécution simulée → reporting).

## Valeur extraite
- Ce qu'on a déjà sous `agent_hub.py` + `agent_control.py` + `agent_loop.py`
  **est** un orchestrateur — la doc valide l'archi.
- Idées supplémentaires : **heartbeat** explicite, kill-switch global (déjà chez
  nous via risk_manager), **journal de décisions** structuré (JSONL pour rejouer).

## Cible d'intégration
- `agent_hub.py` — vérifier que le journal des décisions est rejouable
  (`replay` test). Sinon, ouvrir un ticket.
- `agent_loop.py` — confirmer présence d'un heartbeat avec dernier ts visible.
