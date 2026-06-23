---
source: package/bitget-bot-v4-hardened/ (et `C--Users-jeanf-Desktop-package-bitget-bot-v4-hardened/`)
category: bitget-tooling
action: tool-adapted
target: extraire stratégies / backtests utiles ; pas d'import en bloc
---

## Contenu (extrait)
- `agent_hub_bitget_scalp.py`, `auto_manager.py`, `multi_asset_orchestrator.py`
- `basket_optimizer.py`, `btc_accumulator.py`, `coingecko_feed.py`
- `listing_sniper.py`, `mean_reversion.py`, `market_signals.py`
- **backtests** : `backtest_cta.py`, `backtest_feargreed_accum.py`,
  `backtest_grid.py`, `backtest_grid_breakout.py`, `backtest_scalp_live.py`,
  `backtest_top5_getagent.py`, `backtest_volume_profile.py`
- MT5 : `mt5_backtest.py`, `mt5_connect_test.py`, `mt5_gold_bot.py`
- scripts : `install_termux.sh`, `archive_cleanup.sh`, `list_markets.py`

## Valeur extraite
- C'est un **ancêtre direct** du bot du repo, version « hardened v4 ».
- Les `backtest_*.py` sont précieux : ils encodent les **règles testées** pour
  chaque stratégie (CTA, grid, fear&greed accumulation, volume profile, scalp).
- `basket_optimizer.py` = sizing multi-actifs, possible inspiration pour
  `position_sizer.py`.

## Cible d'intégration
- Ouvrir un par un les `backtest_*.py` pour récupérer **les règles** (pas le code
  brut). Les formaliser dans `docs/RESEARCH_NOTES.md` ou dans
  `order_signal_engine.py` selon le cas.
- `backtest_volume_profile.py` est particulièrement intéressant (cf. fiche
  `pdf_volume_profile_insiders_guide.md`).
- MT5 = hors scope (pas de MT5 dans le repo) → `skipped`.
