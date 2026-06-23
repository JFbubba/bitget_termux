---
source: package/Smart Money Wallet Tracking.docx (+ doublons `(2).docx` et `Markdown/Smart Money Wallet Tracking*.md`)
category: crypto-onchain
action: extracted
target: docs/RESEARCH_NOTES.md (§ « Smart money on-chain »), futur agent on-chain
---

## Sujet
**Suivi de wallets smart-money** : repérer les wallets qui surperforment, tracker
leurs mouvements en temps réel comme signal directionnel.

## Valeur extraite
- Méthodes d'identification : ranking PnL on-chain (Nansen, Arkham), filtres
  d'activité (frais payés > X, % trades gagnants).
- Lecture : **flux nets** (entrée/sortie d'exchange centralisé) plutôt que solde brut.
- Limite : un wallet « smart » aujourd'hui ne l'est pas demain → fenêtre roulante.

## Cible d'intégration
- `docs/RESEARCH_NOTES.md` — § « Smart money on-chain » : règles de scoring de
  wallets, fenêtres roulantes, garde-fous (interdiction de copy-trading aveugle).
- Si volet on-chain s'ouvre : futur agent qui produit un vote
  `smart_money_flow ∈ [-1, 1]` à intégrer à `swarm_brain.py`.
