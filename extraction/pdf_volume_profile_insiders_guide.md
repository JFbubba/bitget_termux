---
source: package/VOLUME-PROFILE-The-insiders-guide.pdf (+ `…-v-1.2.pdf` dans PDF/)
category: method
action: extracted
target: swarm_brain.py (vote VP), order_signal_engine.py, docs/RESEARCH_NOTES.md
---

## Sujet
Volume Profile — distribution du volume par **niveau de prix** (et non par temps) :
POC (point of control), VAH/VAL (value area), HVN/LVN (high/low volume nodes),
single prints.

## Valeur extraite
- **POC** = aimant ; le prix tend à y revenir.
- **VAH/VAL** = bornes statistiques du *fair value* (≈ 70 % du volume).
- **LVN** = vide de liquidité — cassure rapide attendue, ou rejet net.
- **single prints** = signature de mouvement panique → souvent re‑testé.

## Cible d'intégration
- `swarm_brain.py` — vote VP : retourne `{distance_to_POC, in_value_area, lvn_ahead}`.
- `order_signal_engine.py` — règles : entrée fade aux extrêmes value area, breakout
  validé à travers un LVN, target = POC suivant.
- `docs/RESEARCH_NOTES.md` — § Volume Profile avec définitions et règles d'entrée
  test­ables.

## Doublon
La méthode est aussi évoquée dans plusieurs HTML « Darkpool / Investing /
TradingView » → skip (cf. `skip_html_scrap_and_assets.md`).
