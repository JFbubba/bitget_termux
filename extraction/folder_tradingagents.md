---
source: package/TradingAgents/
category: repo-clone
action: extracted
target: docs/RESEARCH_NOTES.md (§ « Cadre multi-agents — référence externe »)
---

## Contenu
- Repo Python complet : `LICENSE`, `README.md`, `pyproject.toml`, `cli/`, `main.py`,
  `test.py`, `tradingagents/`, `uv.lock`.
- C'est très probablement le repo **TauricResearch/TradingAgents** (cf. l'HTML
  associé dans `package/`).

## Valeur extraite
- **Référence publique** ; on n'incorpore pas son code (LICENSE à respecter, et on
  a déjà notre propre stack).
- Lecture utile : voir comment **eux** structurent leurs sub-agents (analyste,
  trader, risk, etc.) et leur boucle ; comparer à `agent_hub.py` / `swarm_brain.py`.

## Cible d'intégration
- `docs/RESEARCH_NOTES.md` — § « Cadre multi-agents — référence externe » avec
  un lien (publique) et 3 points de comparaison.
- Pas de code copié.
