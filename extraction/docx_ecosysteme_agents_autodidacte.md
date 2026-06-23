---
source: package/Écosystème d'Agents IA Autodidacte.docx (+ `.gdoc` pointer)
category: agent-architecture
action: extracted
target: docs/RESEARCH_NOTES.md (§ « Apprentissage online »), swarm_brain.py
---

## Sujet
Idée d'un **écosystème autodidacte** — les agents apprennent en continu (online)
de leurs décisions et de leurs erreurs.

## Valeur extraite
- **Hedge weights** (déjà chez nous dans swarm_brain) = brique de base de
  l'autoamélioration.
- Étendre à la **sélection de features** : marquer la pertinence locale de chaque
  feature et la dégrader en cas de non-information mutuelle prolongée.
- **Garde-fou** : ne JAMAIS auto-changer les seuils de risque (kill-switch,
  position cap, stop distance) — l'auto-apprentissage s'applique aux **votes**,
  pas aux limites de sécurité.

## Cible d'intégration
- `swarm_brain.py` — ajouter (si pas déjà) un score de pertinence par feature qui
  décroît si la feature n'apporte rien sur N décisions.
- `risk_manager.py` — vérifier que ses seuils ne sont **pas** modifiables par
  l'apprentissage online (seulement par config humaine).
- `docs/RESEARCH_NOTES.md` — § « Apprentissage online : ce qui apprend vs ce qui
  est figé » avec la frontière claire.
