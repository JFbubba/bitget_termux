---
source: package/Python/ (27 fichiers `bitget_*.py` + `auto_trading_system.py`)
category: bitget-tooling
action: tool-adapted (déjà couvert par le repo)
target: code Bitget existant du repo
---

## Contenu (extrait)
- `auto_trading_system.py`
- `bitget_api.py`, `bitget_sdk.py`, `bitget_official.py`, `bitget_v2.py`
- `bitget_direct.py`, `bitget_complete.py`, `bitget_pro.py`, `bitget_ultra.py`,
  `bitget_final.py`, `bitget_working.py`
- `bitget_hedge.py`, `bitget_hedge_mode.py`, `bitget_hedge_sl.py`,
  `bitget_switch_mode.py`
- `bitget_sl_tp.py`, `bitget_embedded_sl.py`, `bitget_native_sl.py`,
  `bitget_tpsl_fix.py`
- `bitget_check.py`, `bitget_check2.py`, `bitget_test.py`, `bitget_fix.py`
- `bitget_analysis.py`, `bitget_positions_full.py`, `bitget_close.py`,
  `bitget_tasks.py`

## Valeur extraite
- **27 itérations** sur le même problème (interaction Bitget REST/SDK) — pile
  technique éparpillée, beaucoup de doublons d'idée.
- Le repo a déjà sa surface stabilisée (`bitget_balance_reader.py`,
  `execution_gateway.py`, etc.) — ces fichiers sont surtout intéressants pour
  **récupérer un cas d'usage** précis qui manquerait (ex. switch hedge/one-way,
  pose SL natif vs embedded).

## Cible d'intégration
- **Pas d'import en bloc.** Si on a un trou fonctionnel (ex. SL natif TP/SL en
  hedge mode), aller piocher la version qui marche dans `bitget_hedge_sl.py` ou
  `bitget_native_sl.py`, l'adapter, et la mettre dans la surface stable du repo.
- Aucune action immédiate.
