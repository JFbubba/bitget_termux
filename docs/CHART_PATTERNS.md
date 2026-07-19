# chart_patterns.py — figures chartistes objectives (complément de wyckoff_lab)

## Ce que c'est

Un détecteur de **figures chartistes classiques** — objectif, **look-ahead-free**, PUR — greffé sur
les pivots fractals de `price_action.swing_points`, et mesuré par le **même harnais strict** que
`wyckoff_lab` (net de frais, HAC/Newey-West, Deflated Sharpe déflatée, walk-forward, permutation,
benchmark buy-and-hold). C'est le **complément** des événements « climax de volume » de Wyckoff
demandé le 19/07 : *pas* un labo parallèle, mais des figures qui s'ajoutent aux climax, avec les
**indicateurs comme confirmation** (« les indicateurs renforcent une confirmation »).

Classé **SAFE** (`security_agent.FILES_TO_SCAN`) : LECTURE SEULE, AUCUN ordre, AUCUN secret, aucun
chemin d'exécution. **Défaut OFF** (sans verbe CLI : statut only).

## Les 16 figures détectées

À N pivots exacts (fenêtre glissante sur le zigzag alterné H/L) :
`double_top`/`double_bottom`, `triple_top`/`triple_bottom`, `head_shoulders`/`inverse_hs`.
À deux lignes (2 derniers hauts + 2 derniers bas, pentes/convergence) :
`ascending_triangle`/`descending_triangle`, `sym_triangle_long`/`sym_triangle_short`,
`rising_wedge`/`falling_wedge`, `rectangle_long`/`rectangle_short`.
Continuation d'impulsion : `bull_flag`/`bear_flag`.

## Look-ahead-free (la règle d'or)

Une figure est **détectée à sa barre de CONFIRMATION `t`** = la clôture qui casse la
neckline/ligne, et **tous ses pivots** sont strictement antérieurs et **déjà confirmables**
(`indice_pivot + k ≤ t`, car un pivot fractal n'est connu que `k` barres après). Entrée open
`t+1` (gérée par le harnais). **Aucune fenêtre centrée, aucun lissage bilatéral, aucun pivot
futur** — les pièges exacts des libs publiques (`PatternPy`/`TradingPatternScanner` utilisent
`.shift(-1)` = barre future ; `tradingpatterns_tech.py` lisse avec Savitzky-Golay/Kalman/wavelet
centrés = fuite temporelle massive). Test unitaire de causalité : détecter sur la série tronquée
`[:t+1]` reproduit `t`, et `[:t]` ne le contient PAS.

## Confluence : les indicateurs comme confirmation

Chaque confirmation peut être filtrée par confluence, et le labo MESURE si ça aide :
- **`volume`** : la barre de cassure a un volume ≥ 1,2 × SMA(volume, 20) des barres antérieures ;
- **`full`** : volume ET RSI non-épuisé (long : RSI ≤ 72 ; short : RSI ≥ 28) ET tendance SMA50
  alignée (long : close > SMA50 ; short : close < SMA50) ;
- **`wyckoff`** : un **climax Wyckoff de même sens** (`wyckoff_lab.detect_events`) dans les ≤ 5
  barres précédant la cassure — c'est le « complément Wyckoff » (figure confirmée par le volume-climax).

## Ancrage de Grok

`grok_vision.cross_wyckoff` détecte désormais aussi les **figures objectives** dans la fenêtre
récente (`objective_patterns`), et `grok_vision.agreement` **recoupe les figures nommées par Grok**
avec elles (`pattern_overlap`, normalisation fr/en/sigles « H&S »→head shoulders). Grok ne se voit
PAS imposer les figures dans son prompt (pour ne pas biaiser sa lecture) — elles servent de
**cross-check reproductible** de ses affirmations, mesuré comme le reste.

## Prior HONNÊTE (avant mesure)

Les figures « dessinées à l'œil » sont subjectives et data-snoopables. Lo-Mamaysky-Wang (2000) ne
trouvent qu'un edge marginal — et avec un **noyau bilatéral non réalisable en temps réel** ;
Sullivan-Timmermann-White (1999) montrent que la « meilleure » règle perd sa significativité une
fois corrigé le data-snooping. Bulkowski chiffre des **break-even failure rates** élevés :
rising_wedge **51 %**, flags/pennants **44-54 %** (≈ pile/face) ; les moins mauvais sont
double/triple bottom, inverse H&S, falling wedge, ascending triangle. En **intraday crypto** avec
~6 bps/côté, le prior est **edge nul** ; en haute-TF l'edge brut existe sur les grands
retournements rares mais donne **trop peu d'instances** → massacré par la Deflated Sharpe. Le dépôt
a déjà rejeté SMC/ICT/Wyckoff (tous fee-killed, ERR-014).

## Verdict (19/07) — réel-non-tradable, prior tenu

`--run-all` (8 majors × M1..W1 × 16 figures × 5 horizons × 4 modes de confluence, N_trials=2560) :
- **figure gagnante** : `sym_triangle_long` 1D h=1 full-confluence, net maker **162 bps/trade**,
  t_HAC 2,51, n=57 → mais **DSR = 0,138 ≪ 0,95** : écrasée par la déflation. Les gros chiffres
  (inverse_hs 1D +183 bps, bear_flag 1W +1084 bps) sont sur haute-TF à **petit n (30-35)** — le
  piège small-sample que la théorie prédit. Aucune config ne passe le gate (net>0 ∧ t_HAC≥3 ∧ DSR≥0,95).
- **effet de la confluence** (net maker moyen pondéré, réponse mesurée à « les indicateurs
  renforcent la confirmation ») : `none` **−1,24** bps → `volume` **−0,12** → `full` **−0,09** bps.
  Les indicateurs **réduisent bien la perte** (ils filtrent les pires cassures — l'intuition est
  directionnellement JUSTE) mais **ne basculent PAS** le net positif. La confluence `wyckoff` est
  trop rare (n petit) et sélectionne de moins bons points (**−10,88** bps).

**Conclusion** : les figures chartistes restent **fee-killed / non robustes** ; le détecteur est un
**instrument de mesure et d'ancrage** (défaut OFF, aucune voix branchée). La confluence indicateurs
est le seul levier qui bouge l'aiguille, et seulement pour rapprocher de zéro. Rouvrir uniquement si
frais ≈ 0 (VIP), ou univers 100+ coins pour donner du n à la haute-TF, ou en input d'un modèle
d'ensemble.

## Usage

```bash
python chart_patterns.py --status [SYMBOL]      # config + disponibilité data (consultation)
python chart_patterns.py --run BTCUSDT 4H       # figures détectées + forward net (lisible)
python chart_patterns.py --run-all              # univers × TF × figures × confluence + verdict
```

Artefact de résultats : `.chart_patterns_result.jsonl` (gitignoré via le glob `*.jsonl`).

## Fiabilité Bulkowski (référence, barres daily actions — brut, hindsight)

| Figure | Break-even failure rate | Mouvement moyen |
|---|---|---|
| Inverse H&S (bull) | ~4 % | +38 % |
| Triple bottom (bull) | 13 % | +46 % |
| Double bottom (bull) | 16 % | +39 % |
| Head & Shoulders top (bear) | 19 % | −16 % |
| Descending triangle (bear) | 23 % | −15 % |
| Double top / Triple top (bear) | 25 % | −14/15 % |
| Symmetrical triangle | 25 % | +34 % |
| Falling wedge (bull) | 26 % | +38 % |
| Bull/Bear flag | 44-45 % | +9/−8 % |
| Rising wedge (bear) | **51 %** | −9 % |

Ces mouvements sont mesurés jusqu'au plus-haut/bas **ultime** (hindsight), sur semaines-mois en
daily, **brut** — PAS des espérances par trade encaissables. C'est précisément pourquoi la mesure
net-de-frais du dépôt les rejette.
