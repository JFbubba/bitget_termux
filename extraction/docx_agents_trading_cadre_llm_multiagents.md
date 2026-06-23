---
source: package/Agents de trading _ Cadre de trading financier LLM multi-agents.docx (+ `1.docx`)
       (+ doublons `Aa dossi/Agents de trading…docx` et `dossier_tradingagents_echange_complet*.docx`)
category: agent-architecture
action: extracted
target: docs/RESEARCH_NOTES.md (§ « Cadre multi-agents »), agent_hub.py, swarm_brain.py
---

## Sujet
Document long sur un **cadre multi-agents LLM** pour la finance (rôles spécialisés :
analyste fondamental, technique, news, risk, exécution, supervisor).

## Valeur extraite
- **Pattern d'orchestration** : un supervisor route les requêtes vers des sub-agents
  spécialisés ; chacun a son outillage propre (read-only par défaut).
- **Aggregation** : vote pondéré ou consensus minimal, exactement la philosophie
  de `swarm_brain.py` — bonne validation que l'archi du repo converge.
- **Anti-LLM-hallucination** : chaque sub-agent doit citer la **donnée brute**
  qu'il a lue (timestamp, source), pas reformuler de mémoire.

## Cible d'intégration
- `agent_hub.py` — vérifier la séparation supervisor / sub-agents et la traçabilité
  des données utilisées par chaque décision.
- `swarm_brain.py` — voir si on peut **ajouter** un sub-agent "news" / "fondamental"
  comme expert pondéré (faible poids initial, ajusté online).
- `docs/RESEARCH_NOTES.md` — § « Cadre multi-agents » avec les patterns valides.
