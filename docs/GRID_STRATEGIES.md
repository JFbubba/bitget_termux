# GRID_STRATEGIES — traité de grid trading distillé + verdict mesuré

**But** : capture DURABLE du savoir grid trading (les ~17 variantes triées honnêtement),
la synthèse optimisée retenue, le tableau d'indicateurs à mesurer, et le VERDICT mesuré du
banc `grid_lab.py`. À consulter AVANT de (re)proposer une grille — pour ne pas re-mesurer
ce qui est déjà mort. Toutes les mesures : `grid_lab.py` (LECTURE SEULE, aucun ordre).

Prior du dépôt (confirmé ici) : la grille est **fee-killed en taker** et le seul levier est
l'**exécution maker** (cf. mémoire `exec-fees-lever`, `orderflow-edge-verdict`). Ce document
teste si le maker (8 bps/côté, déduction BGB) fait basculer quoi que ce soit. **Il ne le fait
pas** — détail plus bas.

**Correction d'un mythe** : « la grille est écartée car elle exige des annulations d'ordres »
est CADUC. Le market maker (`market_maker.py` §94) annule déjà des ordres (`futures_cancel_orders`
est légitime, cf. `security_agent`), et la clé Bitget Trade-only interdit les **retraits**, PAS
les **annulations**. La grille n'est donc PAS écartée pour une raison de permissions — elle est
écartée pour une raison **économique** (frais + piège de la cassure), mesurée ici.

---

## 1. Tri honnête des variantes de grille

Pour chaque variante : où elle se mappe dans le bot OU pourquoi elle est fee-killed / redondante.

| # | Variante | Description | Verdict / mapping |
|---|---|---|---|
| 1 | **Spot ATR-adaptative (géométrique)** | Bornes = VWAP ± k·ATR, niveaux à % constant, activée en consolidation, coupée sur cassure | **RETENUE comme synthèse** → `grid_lab.py`. **MESURÉE fee-killed** (0/16 BTC+ETH M1..W1, cf. §4) |
| 2 | **Core + grille (hybride)** | Poche d'inventaire core (B&H) + grille par-dessus | Option `core_notional` du banc. Le « core » = simplement du **beta** (= B&H) ; le core spot BTC réel = `accumulation_engine`+`spot_executor` §44 (INTOUCHABLE). La grille par-dessus n'ajoute pas d'alpha (mesuré) |
| 3 | **Asymétrique haussière** (biais long) | Plus de barreaux d'achat que de vente, ou tailles asymétriques | = pari directionnel déguisé → relève du **cerveau/edge_ladder**, pas d'une grille. Si l'on croit à la hausse : accumuler (§44), pas griller |
| 4 | **Grille trailing plafonnée** | Recentrage des bornes qui suit le prix (plafonné) | Recentrage périodique DÉJÀ dans la synthèse (redéploiement en consolidation). Le « trailing » qui suit une TENDANCE = anti-thèse de la grille (grille = range). Fee-killed comme le reste |
| 5 | **Infinity grid** (sans borne haute) | Grille qui ne coupe jamais en haut, rachète indéfiniment | **REJETÉE** : viole le cap d'exposition anti-martingale (exposition non bornée) et le principe « pas d'élargissement auto ». C'est du DCA non contrôlé sur la jambe haute |
| 6 | **Breakout-retest grid** | Déploie la grille APRÈS une cassure+retest confirmé | = signal directionnel de structure → **strategy_lab / SMC** (déjà mesuré REJETÉ, `docs/VERDICTS.md`). Pas une grille de range |
| 7 | **Pair / spread statistique (grille de z-score)** | Grille sur le spread de deux actifs co-intégrés | Mappé à `strat_pairs` (strategy_lab) + `carry_agent`. Le cœur crypto = **UN beta** (corr 77-88, mémoire `universe-correlation-structure`) → peu de vraies paires ; testé perdant côté signal |
| 8 | **Funding-sensible (perp)** | Grille sur perp modulée par le funding | Le funding est déjà exploité (`carry_agent`, `funding_fade` §75). Sur SPOT (objet du banc) il n'y a pas de funding. Redondant |
| 9 | **Martingale / anti-martingale doublante** | Double la taille à chaque niveau adverse | **À EXCLURE catégoriquement** : ruine à queue épaisse, viole le cap d'exposition en dur. Non implémentée, non mesurée (interdite par conception) |
| 10 | Grille arithmétique (pas fixe en $) | Niveaux équidistants en prix | Dominée par la géométrique (% constant capture un rendement constant par cycle). `strat_grid` existant est de ce type mais c'est un SIGNAL, pas une grille à inventaire |
| 11 | Grille neutre (delta-hedgée) | Grille + short perp pour neutraliser le delta | Ajoute des frais de perp + funding des 2 côtés → aggrave le problème de frais. Fee-killed a fortiori |
| 12 | Grille à volatilité-targeting | Espacement ∝ volatilité réalisée | Partiellement dans la synthèse (bornes ATR-adaptatives). L'espacement lui-même reste soumis à la règle d'or ≥3× coûts → borne basse dure |
| 13 | Grille multi-actifs (diversifiée) | Même grille sur N actifs peu corrélés | Buter sur la corrélation (cœur crypto = 1 beta). Diversifiants réels = XAUT/actions tokenisées (mémoire corrélation) — hors périmètre spot liquide du grid |
| 14 | Grille à réinvestissement composé | Réinjecte les profits en tailles croissantes | Croissance des tailles = dérive vers la martingale douce → plafonnée (linéaire max) par le cap. N'change pas le signe du résultat net |
| 15 | Grille « maker-only » stricte | Uniquement des ordres limites (jamais taker) | La synthèse fait déjà les fills de grille en MAKER. MAIS le **seed** initial et la **coupe** sont taker par nature (acheter au-dessus du prix / stopper une cassure). Le maker-only pur = grille long-only sans seed = **DCA** (= `accumulation_engine` §44) |
| 16 | Grille bornée par support/résistance (profil de volume) | Bornes = HVN/LVN au lieu de ATR | `technicals._volume_nodes` existe ; testable en swappant le `center`/bornes. Marginal : ne change pas l'économie frais+cassure |
| 17 | Grille « range-then-trend » adaptative | Bascule grille↔momentum selon le régime | = régime-switching. Le régime est un instrument de **VOL/sizing** (mémoire `pypi-tools-watchlist`), pas un générateur d'edge directionnel (gate de régime REJETÉ ×2, §104) |

**Synthèse du tri** : 1 variante retenue et mesurée (la #1, la meilleure synthèse), 5 mappées à
des modules existants (2,7,8,11,15→§44), 4 rejetées par principe (5,9 et dérivés martingale),
le reste dominé/redondant. **Aucune ne franchit le mur des frais** une fois mesurée.

---

## 2. Synthèse optimisée retenue (implémentée dans `grid_lab.py`)

1. **Espacement GÉOMÉTRIQUE** : niveaux `lo·(1+g)^j`, `N = ⌊ln(hi/lo)/ln(1+g)⌋`, borné `max_levels`.
2. **Bornes ATR-adaptatives** : centre = **VWAP** (repli SMA), `[centre−k·ATR, centre+k·ATR]`, k∈[2,4].
3. **Filtre de régime (activation)** : déploie SEULEMENT si **ADX < seuil (~22)** ET largeur de
   Bollinger stable (≤ `bb_expand_max`× sa SMA) ET volume non-expansif. ADX = Wilder, porté et
   testé DANS le labo (n'existe pas en prod hors scratchpad).
4. **Coupe sur cassure (sortie disciplinée)** : clôture hors range OU ADX > `adx_exit` OU
   expansion ATR (> `atr_exit_mult`× ATR-au-déploiement) OU pic de volume → **liquide l'inventaire
   au marché et reste FLAT** jusqu'à la prochaine consolidation. JAMAIS d'élargissement automatique.
5. **Porte ≥3× coûts (règle d'or)** : `g ≥ 3·(2·frais + 2·slippage)`. À 8 bps + 2 bps slip →
   espacement mini ≈ **0,6 %**. En-dessous = rejeté (`viable_3x=False`).
6. **Comptabilité TOTAL-P&L** : `total = grid-profit réalisé − frais + P&L latent (mark-to-market)`.
   JAMAIS le grid-profit seul (piège). Identité vérifiée par test.
7. **Cap d'exposition ANTI-MARTINGALE** : barreaux de taille FIXE ; `exposition_max ≤ max_levels·rung`
   (mesurée au COÛT, bornée) ; aucun ajout de niveau après lancement.
8. **Hybride core+grille (optionnel)** : poche B&H séparée (`core_notional`), défaut 0. Le core réel
   §44 reste intouchable — c'est une option de SIZING du banc, pas un branchement.

**Modèle de fills (honnêtetés)** : fill = prix qui traverse le niveau dans la barre (borne SUP,
sans file d'attente) ; 1 transition/cellule/barre (conservateur) ; fills de grille = MAKER,
seed + coupe = TAKER (+ slippage) ; frais maker 8 bps stressés ×{1, 1.5, 2}.

---

## 3. Tableau d'indicateurs à mesurer (tous rapportés par le banc)

| Indicateur | Rôle | Piège évité |
|---|---|---|
| **Total-P&L** | juge final (net de frais) | ne jamais lire le grid-profit seul |
| grid-profit réalisé | spacing capturé + coupes réalisées | positif ≠ gagnant si latent/frais négatifs |
| **P&L latent** (mark-to-market) | expo d'inventaire non soldée | le « profit de grille » cache le latent perdant |
| frais / brut | part des frais | le mur des frais = 1ère cause de mort |
| cycles (round-trips) | activité réelle | 0 cycle = grille jamais remplie |
| temps actif (`frac_active`) | fraction déployée | grille étranglée par un filtre trop strict |
| déploiements / coupes | churn de whipsaw | seed+coupe taker répétés = fuite de frais |
| drawdown max | risque de la courbe | — |
| exposition max (au coût) | capital engagé, borné | garantie anti-martingale |
| **vs buy-and-hold (apparié)** | alpha vs beta | une grille en bull = souvent du beta |
| après funding (perp) | coût de portage | N/A en spot (objet du banc) |
| **PBO / DSR / walk-forward OOS** | robustesse / anti-surtest | in-sample flatteur |
| stress de coûts ×{1,1.5,2} | survie hors point nominal | n'accepter que le robuste au stress |

---

## 4. VERDICT MESURÉ (grid_lab.py, échelle complète M1..W1)

**Setup** : BTC/USDT + ETH/USDT (+ SOL vérifié), M1·M5·M15·M30·H1·H4·D1·W1, frais maker 8 bps/côté
(BGB, spot), slippage 2 bps sur seed/coupe. Sweep 8 configs (espacement × k_atr). Sélection sur
TRAIN (60 %), jugement OOS (40 %). Portes : PBO<0,5 ET DSR≥0,95 ET folds+≥0,6 ET bat B&H apparié
ET survit stress ×2 ET règle d'or 3×coûts.

**Résultat : 0/16 (sym,TF) BTC+ETH survivent. 0/2 SOL. AUCUNE config ne passe.**

- **DSR < 0,95 PARTOUT** (meilleur ≈ 0,55) : aucun Sharpe déflaté significatif une fois le
  multiple-testing pris en compte.
- **OOS Sharpe ≈ 0 ou négatif** partout ; folds+ ≤ 0,4 (jamais ≥ 0,6).
- Les rares TOTAL positifs sont des **artefacts** : BTC W1 +23,64 $ mais **PBO 0,71** (surappris),
  OOS +0,00, DSR 0,29 ; BTC M5 +0,02 mais DSR 0,006.
- Sur D1 le **grid-profit lui-même devient négatif** (BTC −18,68, ETH −2,98, SOL −71,32) : les
  **coupes forcées sur cassure réalisent les pertes** du piège — ce n'est PAS qu'un problème de
  frais, c'est la nature range-only de la grille punie par les tendances crypto.
- Là où le grid-profit est positif (ETH H4 +5,52), **les frais l'annulent** (5,35) → net +0,17,
  OOS −3,03. C'est exactement le levier « exécution/frais » du dépôt : même en maker à 8 bps,
  le churn seed+coupe et le volume de fills paient trop.

**Conclusion honnête** : le grid trading, y compris avec fills MAKER à 8 bps, ne produit AUCUN
edge déflaté, hors-échantillon, battant le buy-and-hold et survivant au stress de coûts, sur
BTC/ETH/SOL de M1 à W1. **Fee-killed ET breakout-trap-killed.** Le maker ne fait basculer aucune
config (contrairement au directionnel futures où le maker avait divisé la perte, mém.
`exit-calibration-verdict`) — parce que la grille multiplie les fills et paie un seed+coupe taker
à chaque whipsaw.

**Ce qu'il faudrait pour rouvrir** (aucun armé ici) : (a) frais ≈ 0 (rabais VIP profond) OU (b)
un actif GENUINEMENT range-bound à faible tendance et vol modérée (rare en crypto liquide). À
re-mesurer seulement si l'un de ces deux changements survient — sinon NE PAS re-tester.

**Statut** : REJETÉ (mesuré perdant). Aucune config à retenir pour une étape ultérieure. Le banc
reste comme instrument de MESURE réutilisable (défaut OFF, lecture seule).

---

## 5. VERDICT COMPARATIF SPOT vs FUTURES (grid_futures_measure.py, 24/07)

La condition de réouverture (a) du §4 — « frais ≈ 0 » — est en partie testable **maintenant** : les
frais **maker FUTURES Bitget = 2 bps/côté**, soit **4× moins cher que le spot** (8 bps BGB). Le banc
`grid_futures_measure.py` (LECTURE SEULE, réutilise `grid_lab`) isole la SEULE variable frais : mêmes
bougies, même sweep 8 configs, mêmes portes ; spot = 8 bps maker + 2 bps slip, futures = 2 bps maker
+ 4 bps slip (modélise le repli taker ~6 bps que le post-only subit sur seed + coupe). Long-only
(pas de short, pas de funding) pour que le frais reste le facteur DOMINANT du verdict.

**Setup** : BTC + ETH + SOL, échelle complète M1·M5·M15·M30·H1·H4·D1·W1 = **24 cellules × 2 régimes**.

**Résultat : SPOT 0/24 · FUTURES 0/24. Les frais 4× plus bas ne font basculer AUCUNE cellule.**

- **DSR < 0,95 PARTOUT, les deux régimes.** Meilleur DSR de tout le balayage (48 mesures) :
  **ETH M30 futures 0,7038** — le MAX, sélectionné sur multiple-testing, toujours **sous la porte**.
  BTC M1 futures 0,4972 (spot 0,4538) ; ETH W1 = 0,00 (aucune puissance, peu de barres). **Aucune niche.**
- **L'avantage frais est réel PAR FILL mais à DOUBLE TRANCHANT.** À frais futures, `cost_ar = 2·(2+4)/1e4
  = 0,0012` → l'espacement 0,4 % **passe la règle d'or 3×coûts** (interdit en spot). Le sweep sélectionne
  alors des grilles **plus serrées** qui multiplient les fills. Sur les TENDANCES longues, ce churn accru
  **réalise PLUS de pertes aux coupes** : ETH D1 futures −33,79 $ (vs spot −9,62 $), ETH H4 frais 2,69 $
  mais total quand même sous porte, BTC H4 futures −5,89 $ (vs spot −2,35 $, DSR 0,134 < 0,178). Le frais
  bas n'achète PAS de la viabilité — il **déplace la sélection vers le churn**.
- **Où le frais aide vraiment** (TF courts M1–M30, fills nombreux) : DSR futures > spot dans ~11/12 cas
  (BTC M5 0,102→0,245 ; ETH M30 0,531→0,704 ; SOL M30 0,158→0,362). Mais l'amélioration part de ~0,1–0,5
  et **plafonne à 0,70** — jamais 0,95. Le levier « exécution/frais » (mém. `exec-fees-lever`) réduit la
  perte SANS la basculer, exactement comme sur le directionnel futures (mém. `exit-calibration-verdict`).
- **Les grosses cellules « positives » sont des artefacts de BETA latent** : BTC W1 +23,64/+24,02 $,
  SOL W1 +10,96/+7,97 $, SOL D1 futures +11,64 $ — tenir l'inventaire à travers une jambe haussière =
  buy-and-hold déguisé, recalé par `beats_bh` / PBO / DSR (0,0–0,29, W1 = quasi-aucune barre).

**Conclusion honnête** : diviser les frais par 4 (spot 8 bps → futures 2 bps) **NE ROUVRE PAS** le
grid trading. La condition (a) du §4 est donc **fermée dans sa version accessible** (les 2 bps futures
sont le plancher de frais réel du compte, hors rabais VIP profond). La grille reste **fee-killed ET
breakout-trap-killed** — et sur futures, le frais plus bas aggrave même le piège de cassure en
autorisant des grilles plus serrées. Reste ouverte la seule condition (b) : un actif GÉNUINEMENT
range-bound à faible tendance (rare en crypto liquide) — non observé ici.

**Statut** : REJETÉ sur futures AUSSI (mesuré, 24/07). Instruments conservés (`grid_lab.py` +
`grid_futures_measure.py`, défaut OFF, lecture seule). **NE PAS re-tester** sans un changement de
régime de frais (rabais VIP) OU un actif structurellement range-bound.

---

## 6. VERDICT EXHAUSTIF MULTI-SURFACE (grid_engine, 24/07) — short + delta-neutre + funding

Les §4/§5 mesuraient la grille **long-only**. Le §5 excluait explicitement les leviers que la marge et
les futures débloquent : le **short** (jambes bidirectionnelles, couverture delta-neutre) et le
**funding** (perp). Le moteur `grid_engine.py` (pur, généralisé) + le labo `grid_engine_lab.py` balaient
ces dimensions exhaustivement (angle « C » — la mesure tranche) : `mode {long_only, bidirectional,
neutral} × surface {spot, margin, futures} × funding × 8 configs × 3 symboles × échelle TF M1..W1`.
Design : `docs/superpowers/specs/2026-07-24-grid-engine-multi-surface-design.md`. Combos valides :
spot=long_only (baseline de contrôle, reproduit le §4), marge/futures = bidirectionnel + neutre.
Gardes d'honnêteté (le piège de l'exhaustif) : **déflation DSR sur TOUT le sweep**, **B&H apparié à
l'exposition**, **funding faible-puissance signalé** (`⚠️lowfund` si < 90 fixings 8 h DANS la fenêtre),
non-régression du long-only mort. Frais autoritatifs : spot/marge = 8 bps, futures = 2 bps (+ funding).

**Résultat : 0/120 (sym × TF × combo) SURVIVENT. Le short et le funding ne rouvrent RIEN.**

- **Le hedge delta-neutre fait EXACTEMENT ce pour quoi il est conçu** — il supprime le delta directionnel
  et **DIVISE la perte de cassure** en tendance : BTC D1 spot −25,55 $ → futures/neutral −12,59 $
  (**−51 %**) ; SOL D1 spot −86,13 $ → futures/neutral −38,15 $ (**−56 %**), marge/neutral −44,51 $.
  L'hypothèse « supprimer le delta = supprimer le tueur #2 » est donc **mécaniquement CONFIRMÉE**…
  mais le DSR s'**effondre** (0,001–0,03, PIRE que le spot long-only 0,14–0,51) : le neutre **churne
  davantage** (deux jambes + couverture), il échange la perte contre du **bruit** et ne devient jamais
  viable. Réduire la perte ≠ produire un edge.
- **La meilleure cellule des 120, ETH M30 futures/bidirectional, a DSR 0,9742 (> porte 0,95) — et reste
  ✗** : elle a échoué un AUTRE verrou (bat-B&H / stress ×2 / folds+ / PBO). C'est la **preuve que les
  gardes multi-critères marchent** : un gate à une seule métrique (DSR seul) l'aurait FAUSSEMENT promue.
- **Funding négligeable** (−0,03 à +0,03 $ par cellule sur ce parc) — il ne bascule ni ne sauve rien ;
  le drapeau `⚠️lowfund` se déclenche correctement sur les cellules short-TF (fenêtre funding fine).

**Conclusion honnête** : la grille est **close sur les TROIS surfaces** — long-only (§4/§5) ET
bidirectionnelle ET delta-neutre ET funding-aware. Le seul apport neuf mesuré est **négatif au sens de
l'edge** : le hedge neutre atténue la perte sans jamais franchir la porte, au prix d'un churn qui détruit
le Sharpe. Reste ouverte la seule condition (b) du §4 : un actif GÉNUINEMENT range-bound (rare en crypto
liquide). Ni le short, ni la marge, ni le funding, ni le perp ne changent le verdict.

**Statut** : REJETÉ sur les 3 surfaces, tous modes (mesuré, 24/07). Instruments conservés, défaut OFF,
lecture seule : `grid_engine.py` (moteur pur), `grid_engine_lab.py` (labo — `python grid_engine_lab.py
--run [--quick|--univers]`). L'adaptateur d'exécution `grid_trader.py` reste un **SQUELETTE de sûreté
NON CÂBLÉ** (défaut OFF/DRY, gardes prouvées, `_delegate` lève NotImplementedError — **décision proprio
STOP** : pas de chemin d'ordre réel pour une stratégie sans edge). **NE PAS re-mesurer** sans (a) rabais
de frais VIP profond OU (b) un actif structurellement range-bound. Le câblage live de `grid_trader` (aux
§67, classification `safe_push_check`) n'est à faire QUE si une config franchit un jour la porte.
