---
source: package/Wyckoff-Method-Wyckoff-Analytics-English-V2.pdf (+ doublon dans PDF/)
category: method
action: extracted
target: swarm_brain.py (vote « structure »), order_signal_engine.py, docs/RESEARCH_NOTES.md
---

## Sujet
Méthode Wyckoff — lecture **volume + structure** : phases
Accumulation / Markup / Distribution / Markdown, **springs**, **upthrusts**,
**SOS/SOW** (sign of strength / weakness), **last point of support/supply**.

## Valeur extraite
- **règles concrètes activables** :
  - détection de **range** (PS, SC, AR, ST), puis **spring** (faux casse sous le
    creux suivi d'un retour rapide dans le range).
  - test de la résistance (UT/UTAD) — confirmation de distribution.
  - SOS = bougie d'expansion volumique vers le haut au sortir d'un creux secondaire.
- **volume** : un mouvement de prix sans volume = signal faible ; un creux à
  volume sec = candidat accumulation.

## Cible d'intégration
- nouveau « vote structure » dans `swarm_brain.py` : retourne
  `{phase, spring/ut, confidence}` à partir d'OHLCV+volume.
- `order_signal_engine.py` — utiliser le spring confirmé pour proposer un signal
  long avec SL sous le creux du spring.
- `docs/RESEARCH_NOTES.md` — § « Wyckoff opérationnel » avec définitions et seuils
  testables (longueur de range min, retracement spring, ratio volume).

## Doublon
`Wyckoff — Indicateurs et Stratégies — TradingView.html` + `_files/` couvre le
même sujet en moins dense → skip (cf. `skip_html_scrap_and_assets.md`).
