# Indicateurs « pro traders » — implémentation & sources

Indicateurs recommandés par des traders pro, classés en deux familles :
**(A) calculables localement** (implémentés, purs, testés) et
**(B) macro / cross-asset / microstructure** (nécessitent des flux externes —
documentés ici avec leurs sources, à brancher en **lecture seule**).

Tout reste **aide à la décision** : aucun ordre réel, `can_trade=False`.

---

## A. Calculables localement — `pro_indicators.py` (+ `indicators.py`)

| Indicateur | Fonction | Entrée | Sortie |
|---|---|---|---|
| RSI | `indicators.calculate_rsi` | closes | série RSI |
| Momentum (ROC) | `pro_indicators.momentum` | closes | ROC % |
| Volume profile (POC + value area) | `pro_indicators.volume_profile` | bougies {close, volume} | POC, VA low/high |
| Niveau ancré au volume | `indicators.volume_anchored_level` | bougies {close, volume} | prix S/R |
| Biais volume | `indicators.volume_bias_score` | bougies {open, close, volume} | score signé |
| Ratio de Sharpe | `pro_indicators.sharpe_ratio` | rendements | Sharpe (annualisable) |
| Sizing par risque capital | `pro_indicators.risk_based_position_size` | capital, risk %, entry, stop | taille, montant risqué |
| Timing des canaux horaires | `pro_indicators.trading_sessions` | datetime (Bruxelles) | fenêtres actives |
| Rotation sectorielle XLY/XLP | `pro_indicators.sector_rotation_ratio` | prix XLY, XLP | ratio risk-on/off |
| Positionnement COT | `pro_indicators.cot_net_positioning` | longs, shorts | net, net %, biais |
| **Confluence** signal × micro × macro | `confluence_score.confluence_score` | side + carnet/CVD/biais/régime | label + score |

> **Convergence** : `confluence_score.py` réunit le signal, la microstructure
> (`order_flow` via `bitget_market_data`) et le régime macro (`macro_context`)
> pour dire si tout est ALIGNÉ avec la direction (LONG/SHORT). Advisory, lecture
> seule. CLI : `python confluence_score.py BTCUSDT LONG` ; Telegram :
> `/confluence SYMBOL SIDE`.

### Risk management du capital (principe encodé)
> **Le stop-loss ne protège pas une position, il protège le CAPITAL.**

On ne part pas d'un stop court arbitraire : on fixe d'abord le **risque capital
accepté** (ex. 1 %), puis la **taille en découle** :
`taille = (capital × risque%) / distance_au_stop`.
→ `risk_based_position_size(capital, risk_percent, entry, stop)`. Le stop peut
être large (laisser respirer la thèse) tant que la **perte en capital** reste
bornée par la taille.

### Timing des canaux horaires (heure de Bruxelles)
Fenêtres de plus forte activité encodées dans `TRADING_WINDOWS` :
`09:00–11:00` (EU), `15:30–17:00` (US open) dont `15:30–16:30` (pic),
`01:00–02:00` (Asie). `trading_sessions(dt)` renvoie les fenêtres actives ;
utile pour pondérer/filtrer les signaux selon l'heure.

---

## B. Macro / cross-asset / microstructure — à brancher (lecture seule)

Ces indicateurs ne se calculent pas depuis les seules bougies Bitget : ils
demandent des données externes. Ils servent de **couche de contexte
risk-on / risk-off** au-dessus des signaux crypto.

| Indicateur | Ce qu'il signale pour le crypto | Source gratuite / lecture seule |
|---|---|---|
| **DXY** (indice dollar) | dollar fort = pression baissière crypto | FRED (`DTWEXBGS`/proxy), Yahoo `DX-Y.NYB` |
| **Pétrole / inflation** | régime inflationniste, énergie | FRED (`DCOILWTICO`, `CPIAUCSL`) |
| **VIX (spike)** | pic de peur actions → risk-off, corrélé aux purges crypto | FRED (`VIXCLS`), Yahoo `^VIX` |
| **Yield curve** (2s10s) | inversion = stress macro / récession | FRED (`T10Y2Y`) |
| **Marché actions + rotation sectorielle** | appétit pour le risque, mécanisme *forward-looking* | ETFs sectoriels via FMP / Yahoo |
| **XLY − XLP** (discrétionnaire − staples) | ratio risk-on/off : XLY>XLP = appétit risque | Yahoo `XLY`,`XLP` → `pro_indicators.sector_rotation_ratio` |
| **COT reports** (CFTC) | positionnement hebdo des gros acteurs (futures, incl. crypto) | **cftc.gov** → `pro_indicators.cot_net_positioning` |
| **Order book / CBOT (profondeur)** | murs d'achat/vente, déséquilibre de carnet | API Bitget (depth) ; MCP CoinDesk (orderbook metrics) |
| **Tape / Time & Sales** | flux de trades, gros prints, agressivité acheteur/vendeur | API Bitget (trades) ; MCP CoinDesk (trades) |

### Plan de branchement (ordre prévu, SAFE)
1. **[fait]** CVD / order-flow + zones de liquidation → `order_flow.py` (calcul
   pur) **alimenté par `bitget_market_data.py`** (reader read-only des endpoints
   publics Bitget : merge-depth, fills/tape, open-interest, current-fund-rate).
   CLI : `python bitget_market_data.py BTCUSDT` ; Telegram : `/orderflow [SYMBOL]`.
2. **COT hebdo** depuis cftc.gov → positionnement.
3. **[fait]** Couche macro risk-on/off → `macro_context.py` (VIX, courbe 2s10s,
   DXY via FRED, export CSV public sans clé ; logique de régime pure et testée).
   CLI : `python macro_context.py` ; Telegram : `/macro`. (XLY/XLP, pétrole et
   COT restent à ajouter comme séries supplémentaires.)
4. **prediction-mcp** (Polymarket) côté PC → odds/sentiment (déjà documenté
   dans `docs/EXTERNAL_TOOLS.md`).

Aucun de ces branchements n'introduit `place_order` / `withdraw` / etc. : ce
sont des **lectures de données** transformées en indicateurs de contexte.

---

## Note d'usage
Les fonctions de la famille (A) sont **pures et testées** (`tests_audit.py`) :
elles peuvent être appelées par le moteur de scan ou par un agent d'analyse
Claude sans aucun effet de bord. La famille (B) sera ajoutée comme
*readers* dédiés (un fichier par source), eux aussi en lecture seule.
