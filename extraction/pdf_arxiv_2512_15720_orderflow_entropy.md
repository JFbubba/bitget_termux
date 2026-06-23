---
source: package/2512.15720v1.PDF
category: research
action: learned
target: regime_features (orderflow_entropy), futur agent « gating-magnitude »
status_in_registry: traité
---

## Sujet
arXiv 2512.15720 — entropie de l'order flow comme **mesure de magnitude** (et pas
de direction) du déséquilibre flux acheteur/vendeur.

## Valeur extraite
- **feature** : `regime_features.orderflow_entropy` — entropie de Shannon sur les
  bins de signed volume, fenêtre roulante.
- **lecture** : une entropie *basse* = flux unidirectionnel concentré (alignement
  agressif) ; *haute* = bruit indécis.
- **usage** : NE PAS s'en servir pour prédire la direction ; s'en servir comme
  **gate** pour augmenter/diminuer la conviction d'autres signaux directionnels.

## Cible d'intégration
- nouveau champ `regime_features.orderflow_entropy` dans le pipeline régime.
- futur agent dédié « gating-magnitude » : pondère les votes directionnels selon
  l'entropie courante (haute entropie → vote -> hedge_weight × facteur < 1).
- mention dans `docs/RESEARCH_NOTES.md` (déjà fait selon le registre).
