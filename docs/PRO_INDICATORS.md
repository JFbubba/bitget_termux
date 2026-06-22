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
| **XLY − XLP** (discrétionnaire − staples) | ratio risk-on/off : XLY>XLP = appétit risque | Yahoo `XLY`,`XLP` (calculer le ratio) |
| **COT reports** (CFTC) | positionnement hebdo des gros acteurs (futures, incl. crypto) | **cftc.gov** (téléchargement public gratuit) |
| **Order book / CBOT (profondeur)** | murs d'achat/vente, déséquilibre de carnet | API Bitget (depth) ; MCP CoinDesk (orderbook metrics) |
| **Tape / Time & Sales** | flux de trades, gros prints, agressivité acheteur/vendeur | API Bitget (trades) ; MCP CoinDesk (trades) |

### Plan de branchement (ordre prévu, SAFE)
1. **[couche de calcul faite]** CVD / order-flow + zones de liquidation →
   `order_flow.py` (`cumulative_volume_delta`, `order_book_imbalance`,
   `liquidation_levels`), purs et testés. Reste à brancher le *reader* réseau
   (API Bitget depth/trades + OI/funding) qui alimentera ces fonctions.
2. **COT hebdo** depuis cftc.gov → positionnement.
3. **Couche macro** (DXY, VIX, yield curve, XLY/XLP) via FRED + un connecteur
   crypto (FMP) ou les serveurs MCP de contexte → flag risk-on/off.
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
