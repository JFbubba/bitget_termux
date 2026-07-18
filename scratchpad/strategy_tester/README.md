# Strategy Tester Python (inspiré du MT5 Strategy Tester)

Backtester **événementiel** sur les VRAIES données Bitget (`data_history/`) avec les
frais Bitget. Recrée en Python ce qui fait la valeur du MT5 Strategy Tester —
**sans** son binaire (jamais installé, cf. décision sécurité) et, surtout, **sur nos
marchés** (le MT5 tester ne teste que le forex/CFD du broker). LECTURE SEULE.

## Ce qui est repris du MT5 tester
- **Exécution réaliste** : décision à la clôture de `t` → fill à l'**ouverture de `t+1`**
  (anti look-ahead), prix = open ± demi-spread ± slippage (côté défavorable).
- **SL/TP intrabar** via high/low de chaque barre (mode « OHLC ») ; SL prioritaire si
  SL et TP touchés la même barre (pessimiste).
- **Coûts** : commission par côté, spread, slippage, funding/barre (perp).
- **Rapport complet** : rendement, CAGR, **Sharpe/Sortino**, **max drawdown**,
  recovery factor, **profit factor**, expectancy, win rate, payoff, exposition, equity ASCII.
- **Optimisation + WALK-FORWARD** : optimise en in-sample, **valide en out-of-sample**
  (le « forward testing » — seul rempart contre le sur-ajustement).

## Fichiers
| Fichier | Rôle |
|---|---|
| `engine.py` | Moteur événementiel + `ExecConfig` (frais) + `run_backtest` |
| `metrics.py` | Métriques de perf (annualisées par TF) |
| `report.py` | Rapport texte + equity sparkline |
| `strategies.py` | Stratégies (contrat `strategy_fn(ctx)->{signal,sl,tp}`) : `ema_cross`, `donchian_breakout` |
| `optimize.py` | Grille + `walk_forward` (OOS) |
| `run.py` | CLI |

## Usage
```bash
python3 run.py backtest ema_cross BTCUSDT 1H      # backtest simple + rapport
python3 run.py wf       ema_cross BTCUSDT 1H      # walk-forward out-of-sample
```

## Résultats de démonstration
- `ema_cross 12/48 SL3/TP6` BTC 1H : **−83 %**, Sharpe −1,43, DD −87 %, PF 0,8 → perdant.
- `ema_cross` **walk-forward OOS** BTC 1H : **−36 %**, Sharpe −0,8 → perdant même hors
  échantillon (pas un artefact d'overfit). Cohérent : les crossovers simples saignent
  en frais. C'est le rôle du tester : **le montrer proprement**.

## Écrire sa stratégie
Une fonction `f(ctx)->{'signal':+1/-1/0,'sl':frac,'tp':frac}` (ctx = OHLCV causaux +
position courante + params), l'ajouter à `STRATEGIES`. Le moteur, les frais, le
walk-forward et le rapport sont fournis. Pont avec l'agent testeur mql5 : un candidat
réimplémenté peut être backtesté ici pour un rapport de perf complet (au-delà de l'IC).
```
