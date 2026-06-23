---
source: package/ICT-Breaker-Block-2.pdf
category: method
action: extracted
target: order_signal_engine.py (pattern « breaker »), docs/RESEARCH_NOTES.md
---

## Sujet
ICT (Inner Circle Trader) — **breaker block** : un order block qui s'est invalidé
(prix l'a cassé) puis qui est re-testé dans l'autre sens et **fait support/résistance
inversé**.

## Valeur extraite
- **règle** : repérer un OB haussier cassé → quand le prix revient dessus, il doit
  agir en **résistance** (et inversement).
- **timeframe** : recommandé sur HTF d'abord (1H/4H) puis exécution LTF (5m/15m).
- **filtre** : valide surtout après un **liquidity sweep** (faux move balayant les
  stops opposés).

## Cible d'intégration
- `order_signal_engine.py` — règle « breaker » : si OB cassé puis re-test, proposer
  une entrée contraire avec SL au-delà du wick du sweep.
- `docs/RESEARCH_NOTES.md` — § ICT minimal (breaker + sweep) — pas tout l'écosystème
  ICT, qui est large et propice au noise (cf. `txt_smc_9_concepts.md`).
