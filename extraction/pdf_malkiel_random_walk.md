---
source: package/A Random Walk Down Wall Street.pdf (+ `a-random-walk-down-wall-street.pdf` et `Une Marche Au Hasard…` dans PDF/)
category: canon
action: extracted
target: docs/RESEARCH_NOTES.md (§ « Antidote à l'overfit »)
---

## Leçon canonique
- **EMH faible** : un grand nombre de signaux techniques ressemblent à du bruit
  bien rationalisé — antidote pour ne pas surinterpréter une backtest sympathique.
- **Diversification + faibles frais** > stock-picking malin pour la plupart.

## Cible d'intégration
- `docs/RESEARCH_NOTES.md` — § court « antidote à l'overfit » : exiger pour toute
  nouvelle feature un **protocole de validation hors-échantillon** (SPA + placebo
  reversal — déjà tracé via 2511.08571), sinon on s'invente des signaux.
- Aucun code direct à toucher : c'est un garde-fou méthodologique.
