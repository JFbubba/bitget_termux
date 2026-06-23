---
source: package/agent matrix/
category: agent-architecture
action: extracted
target: docs/RESEARCH_NOTES.md (§ « Prompts système d'agents »)
---

## Contenu
- `AGENTS.md`, `BOOTSTRAP.md`, `HEARTBEAT.md`, `IDENTITY.md`, `SOUL.md`,
  `TOOLS.md`, `USER.md`.
- `trading/` (sous-dossier — à explorer si besoin).

## Valeur extraite
- Pattern « OS d'agents » : un set de prompts système modulaires qui définissent
  identité, outils, heartbeat, bootstrap. Inspiration pour structurer nos
  *system prompts* d'agents.
- Notre repo n'a pas (encore) cette séparation — chez nous chaque agent Python
  porte son prompt en dur.

## Cible d'intégration
- `docs/RESEARCH_NOTES.md` — § court « Décomposer le prompt système d'un agent en
  modules (identité, outils, heartbeat) » — à éventuellement adopter quand on
  multiplie les agents LLM.
- Pas de code à porter pour l'instant.
