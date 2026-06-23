---
source: package/agent_ia_trading_onchain_cahier_de_conception.docx
category: agent-architecture
action: extracted
target: docs/RESEARCH_NOTES.md (§ « Agent on-chain — design »)
---

## Sujet
Cahier de conception d'un **agent IA on-chain** : sources, features, scoring,
boucle de décision.

## Valeur extraite
- Recense les **features on-chain** utiles (flows CEX/DEX, MVRV, SOPR, hash rate,
  active addresses, exchange netflow).
- Boucle : pull on-chain → normaliser → score → vote dans le brain.
- Mention des **délais de mise à jour** par source — important : ne pas mixer
  une feature 24h-lag avec une décision intraday.

## Cible d'intégration
- `docs/RESEARCH_NOTES.md` — § « Agent on-chain — design » avec la liste des
  features et leurs latences.
- Quand on instancie cet agent : un nouveau module dans le repo, vote pondéré dans
  `swarm_brain.py`, faible poids initial.
