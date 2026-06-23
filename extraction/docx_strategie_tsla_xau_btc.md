---
source: package/strategie_trading_TSLA_XAU_BTC.docx
category: strategy-doc
action: extracted
target: portfolio_scanner.py, macro_context.py
---

## Sujet
Stratégie tri-asset **TSLA / XAU (or) / BTC** — diversification entre tech, valeur
refuge et crypto.

## Valeur extraite
- L'idée d'**univers fixe restreint** (3-5 actifs corrélés différemment) est
  saine — c'est exactement ce que fait `portfolio_scanner.py` (BTC, ETH, SOL,
  XRP, XAUT).
- Cross-asset : utiliser le mouvement XAU comme **signal risk-off** indirect.
- TSLA n'est pas sur Bitget — à transposer en proxy (ex. corrélation BTC/SP500).

## Cible d'intégration
- `portfolio_scanner.py` — confirmer que l'univers est bien borné (pas de drift
  vers 50 symboles).
- `macro_context.py` — feature `gold_30d_change` comme proxy risk-off (si
  alimentable via une source externe).
- Pas de nouveau code structurel.
