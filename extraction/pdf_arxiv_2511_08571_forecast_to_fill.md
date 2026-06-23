---
source: package/2511.08571v1.PDF (+ doublon `2511.08571v1 (1).pdf`)
category: research
action: extracted
target: swarm_brain.py (slope_to_prob), docs/RESEARCH_NOTES.md
status_in_registry: traité
---

## Sujet
arXiv 2511.08571 — *Forecast-to-Fill (or)* : conversion d'une pente prédite en
probabilité d'exécution / atteinte d'un niveau, validée par protocole **SPA +
placebo-reversal**.

## Valeur extraite (déjà tracée dans drive_triage)
- **feature** : `slope_to_prob` — mapping pente → proba (fonction monotone, calibrée).
- **protocole de validation** : SPA (Hansen) + test placebo en inversant les
  labels — utile pour invalider les features qui passent SPA par chance.
- **garde-fou** : les chiffres de performance du papier sont suspects → ne pas
  reprendre les Sharpe annoncés tels quels ; ré-évaluer localement.

## Cible d'intégration
- `swarm_brain.py` — exposer un vote `slope_to_prob` (poids appris via hedge).
- `docs/RESEARCH_NOTES.md` — § dédié au protocole SPA+placebo-reversal réutilisable
  pour toute future feature.

## Doublon
`2511.08571v1 (1).pdf` = même contenu, déjà marqué `duplicate_of` dans le registre.
