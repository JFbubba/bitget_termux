---
source: package/Black Protocole et critique du marché du trading.docx (+ `BLACK PROTOCOL - See the trap, strike the core_260612_062438.txt`)
category: strategy-doc
action: extracted
target: docs/RESEARCH_NOTES.md (§ « Pièges du marché »)
---

## Sujet
« Black Protocole » — critique du marché du trading retail et identification des
**pièges récurrents** (manipulation, fake breakouts, chasse aux stops).

## Valeur extraite
- Liste de **pièges** opérationnels : faux breakouts en bas/haut de range,
  stop hunts près des niveaux ronds, gap fills systématiques, divergence
  prix/volume ignorée.
- Posture : "voir le piège, frapper le cœur" — ne pas trader le piège, trader le
  retournement post-piège (similaire au pattern SMC liquidity sweep).

## Cible d'intégration
- `docs/RESEARCH_NOTES.md` — § « Pièges du marché » qui catalogue ces signatures
  et les transforme en **filtres** (ex. retarder l'entrée breakout de N bougies
  pour invalider le faux move).
- `order_signal_engine.py` — ajouter un filtre `is_likely_trap(ohlc, level)` avant
  toute entrée breakout.
