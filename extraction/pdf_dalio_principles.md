---
source: package/Principles - Ray Dalio.pdf (+ `Principles Ray Dalio.pdf` dans PDF/)
category: canon
action: extracted
target: docs/RESEARCH_NOTES.md (§ « Principes opérationnels »), agent_hub.py
---

## Leçon canonique
- **Tout est un système** : décompose le marché en machines causales (taux, crédit,
  productivité, démographie, sentiment). Cherche les **dependencies** et leurs
  délais.
- **Radical truth + radical transparency** : nommer les erreurs, journaliser, ne
  pas masquer un drawdown.
- **Believability-weighted decisions** : pondérer les voix par leur track-record
  vérifié — exactement la philosophie *mixture of experts* qu'on a déjà.

## Cible d'intégration
- `agent_hub.py` / `swarm_brain.py` — confirmer que **chaque expert** a un score
  de believability (track record local) qui pondère son vote.
- `docs/RESEARCH_NOTES.md` — § court qui justifie les hedge weights par
  référence à Dalio.
