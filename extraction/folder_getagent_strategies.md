---
source: package/getagent-strategies/ (et `C--Users-jeanf-Desktop-package-getagent-strategies/`)
category: bitget-tooling
action: extracted
target: docs/RESEARCH_NOTES.md (§ « Stratégies GetAgent »)
---

## Contenu
- `btc-ema-cross-demo/` — démo cross EMA sur BTC.
- `btc-ema-cross-demo.tar.gz` — archive du même.
- `run_result.json` — résultat d'une exécution.

## Valeur extraite
- Une **stratégie GetAgent** packagée : EMA cross BTC.
- Le `run_result.json` permet de voir le **format de sortie** attendu par la
  plateforme GetAgent (Bitget) — utile si on publie nous-mêmes une stratégie.

## Cible d'intégration
- `docs/RESEARCH_NOTES.md` — § court « Format GetAgent (Bitget) » avec un
  squelette : nom, version, fonction principale, paramètres, format de retour.
- Pas de code à incorporer ; l'EMA cross est trop trivial pour le repo et
  servait juste de démo.
