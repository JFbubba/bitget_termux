---
source: package/agent hub/ et package/agent_hub/
category: agent-architecture
action: tool-adapted (déjà couvert)
target: agent_hub.py (déjà dans le repo)
---

## Contenu
- Deux dossiers quasi-identiques (un avec espace, un avec underscore).
- Tous deux ont structure pnpm/Node : `package.json`, `pnpm-workspace.yaml`,
  `packages/`, `scripts/`, `tests/`, `docs/`.
- `agent_hub/` a en plus `node_modules/` (installé) et `start-bitget-mcp.mjs`.

## Valeur extraite
- C'est une **autre implémentation** d'un agent hub (Node/TypeScript) — pas la
  nôtre (la nôtre est Python `agent_hub.py` au root).
- Intérêt limité : la nôtre est en place, en Python, intégrée au reste du repo.
- À regarder seulement si on cherche une référence d'**API HTTP** ou de **schéma
  de tools** pour LLM côté Node — sinon on s'évite la stack pnpm.

## Cible d'intégration
- Aucun code à recopier.
- Si on a besoin d'inspiration MCP, voir `start-bitget-mcp.mjs` (le seul fichier
  un peu spécifique) — sinon `skipped`.
