# WYCKOFF_LAB.md — banc de mesure « climax de volume » (verdict net-de-frais)

**Fichier** : `wyckoff_lab.py` (SAFE, lecture seule, défaut OFF, AUCUN ordre).
**But** : mesurer si le SEUL angle Wyckoff falsifiable — les **climax de volume objectifs,
look-ahead-free** (proxy SC/BC + spring/upthrust intrabar, connus AU CLOSE) — porte un rendement
forward **net de frais**, avec une barre anti-sur-testing (t HAC + Deflated Sharpe + walk-forward
OOS + shuffle + contrôles positifs + benchmark B&H). Conçu dans `docs/WYCKOFF.md` Partie IV.
Prior honnête pré-enregistré : **probablement fee-killed en taker** (docs/WYCKOFF.md Partie II).

## Pourquoi ce labo (et pas « Wyckoff »)
Wyckoff comme **méthode** (lecture discrétionnaire de phases : composite man, springs/UTAD
*confirmés*, comptage P&F) = **même piège que SMC/ICT** (rejetés, ERR-014) : look-ahead
intrinsèque (un spring n'est un spring qu'APRÈS le test réussi), labellisation discrétionnaire,
multiple-testing massif. **Ne rien brancher au banc gelé §62.** La seule nuance juste : Wyckoff
met le **VOLUME au centre**, et le volume anormal a une signature académique réelle
(high-volume return premium, Gervais-Kaniel-Mingelgrin 2001 ; sur-réaction crypto post-choc,
Caporale-Plastun 2020). Donc un sous-ensemble est **objectivement définissable au close, sans
look-ahead** : c'est ce que ce labo mesure, rien d'autre.

## L'événement (100 % connu au close de t, AUCUN look-ahead)
- `vol_z = (vol[t] − mean(vol, N trailing)) / std(vol, N trailing) ≥ z` (N=100, fenêtre
  **excluant** la barre courante → le climax se démarque de son propre passé) ;
- **range large** : `high−low ≥ 90ᵉ percentile trailing` du range ;
- **contexte** : nouveau plus-bas N-barres (SC/spring) / plus-haut N-barres (BC/upthrust) ;
- **close-location** `CLV=(close−low)/(high−low)` : SC → CLV≥0,6 (long) ; BC → CLV≤0,4 (short) ;
- **spring intrabar** : `low[t] < min(low, M=20 trailing)` ET `close[t] > min(low, M)` (fausse
  cassure refermée au-dessus) ; **upthrust** = miroir. Sur ce labo à thème climax, spring/upthrust
  exigent AUSSI `vol_z≥z` (shakeout à volume — déviation ASSUMÉE vs la variante prix-seule du
  design, annotée : on reste on-theme et look-ahead-free).
- **Entrée open t+1** ; SC/spring → long, BC/upthrust → short. Sortie open t+1+h.

## Mesure & validation (barre anti-sur-testing)
- Rendement forward **net de frais** à h∈{1,2,4,8,16}, **taker ET maker** (défauts futures 6/2
  bps/côté ; frais réels via `fee_rates` avec `--live-fees` ; spot 10/8 exposés en param) ;
- **échelle TF COMPLÈTE** M1·5m·15m·30m·H1·H4·D1·W1 (ERR-001) ; **univers liquide** : BTC, ETH,
  SOL, BNB, XRP, DOGE, ADA, LINK (exclut alts fragiles où la VSA casse) ;
- **t HAC/Newey-West** (`audit_core.nw_tstat`) — corrige le t gonflé par l'autocorrélation des
  positions persistantes ;
- **Deflated Sharpe** exacte (`audit_core.deflated_sharpe`, Bailey-LdP) sur **N_trials = TF×h×
  directions×seuils = 8×5×4×3 = 480** ;
- **walk-forward OOS** : le seuil z est choisi sur le TRAIN, évalué en OOS uniquement ;
- **permutation/shuffle** : l'edge doit s'effondrer contre un tirage aléatoire de même sens/frais ;
- **contrôles positifs** : réversion 1h connue (gross) + oracle synthétique (peek non-tradable,
  sanity du harnais) — le harnais doit détecter un vrai effet ;
- **benchmark buy-and-hold** apparié (alpha vs beta, ERR-014).
- **Critère PRÉ-ENREGISTRÉ (PASS)** : net>0 OOS ∧ t_HAC≥3 ∧ DSR≥0,95 ∧ cohérent ≥2 TF adjacents
  ∧ > B&H. Sinon → **réel-non-tradable** (on ne branche rien).

## Réutilisation (ne recode rien)
`audit_core` (HAC/DSR validés Monte-Carlo, `scratchpad/audit_indep/`) · `candles_history` /
`data_history/` (bougies mix profondes) · `fee_rates` (frais réels, lecture seule fail-safe).

## CLI
```
python wyckoff_lab.py --status [SYMBOL]      # config + disponibilité data (consultation)
python wyckoff_lab.py --run SYMBOL [GRAN]    # 1 symbole, grille events×h (z primaire)
python wyckoff_lab.py --run-all              # univers × échelle TF + validation + verdict
                                             # option --live-fees : frais réels du compte
```
Défaut OFF : sans verbe CLI, le module n'imprime qu'un usage. Sortie = console + artefact
`.wyckoff_lab_result.jsonl` (UN objet JSON ; suffixe `.jsonl` choisi pour hériter du glob
gitignore existant `*.jsonl` sans éditer `.gitignore`).

## RÉSULTAT MESURÉ (run-all, 19/07/2026 — frais futures 6/2 bps, univers 8 majors)

**Meilleur par TF (maker, net bps/trade) :**

| TF | événement | h | n | net **taker** | net **maker** | t_HAC |
|---|---|---|---|---|---|---|
| 1m | sc_long | 16 | 477 | **−5,4** | +2,6 | 1,49 |
| 5m | sc_long | 8 | 268 | **−0,5** | +7,6 | 1,96 |
| 15m | sc_long | 2 | 281 | +13,6 | +21,6 | **3,69** |
| 30m | sc_long | 4 | 287 | +14,0 | +22,0 | 2,13 |
| 1H | sc_long | 16 | 390 | +87,3 | +95,3 | **3,57** |
| 4H | sc_long | 4 | 117 | +142,9 | +150,9 | 2,43 |
| 1D | sc_long | 2 | 20 | +178,8 | +186,8 | 1,33 |
| 1W | upthrust_short | 16 | 20 | +2398,9 | +2406,9 | 3,07 |

**Tête d'affiche (max Sharpe maker, n≥50)** : `sc_long 4H h=4 z=3,5`, n=117, net maker **+150,9**
bps, net taker **+142,9** bps, t_HAC **2,43**, alpha vs B&H +140,4.
- **Deflated Sharpe = 0,054** (≪ 0,95) : SR0 attendu sous H0 sur 480 essais = **0,423** > Sharpe
  du gagnant **0,264** → le meilleur config ne bat même PAS la chance du data-snooping.
- walk-forward OOS : z\*=3,5, net_OOS **+304,9** bps, t_OOS **3,28**, n=39 (positif mais split unique).
- permutation : obs +150,9 vs null +8,3±95,5, **p=0,004** (les entrées climax battent l'entrée
  aléatoire de même sens — effet directionnel FAIBLE mais réel).
- **plus significatif n≥50** : `spring_long 1m` t_HAC **−11,6** (les springs 1m PERDENT fort),
  DSR 0,000.
- **pic sur-appris (HORS gate)** : `upthrust_short 1W h=16` n=20, +2407 bps — artefact
  small-sample/overlap, écarté du verdict, DSR global 0,76.

**Contrôles positifs (le harnais fonctionne)** : réversion 1h gross **+6,0 bps t_HAC=6,75**
(n=23 289 — effet connu détecté sur le brut) ; oracle peek **t_HAC=44,2** (énorme — le harnais
sait détecter un vrai edge, comme les contrôles t≈5,8 de l'étude arXiv de falsification).

**Gate (5 critères)** : net_OOS>0 ✅ · t_HAC≥3 ❌ (2,43) · DSR≥0,95 ❌ (0,054) ·
cohérent 2 TF adjacents ❌ (15m ✅ et 1H ✅ passent net>0 & t≥3, mais **non adjacents** — 30m
entre eux échoue) · bat B&H ✅. → **2/5**.

## VERDICT : réel-non-tradable
Le climax de volume objectif a une **tendance directionnelle faible et réelle** (entrées
battent l'aléatoire p=0,004, OOS positif à 4H, alpha>0), **conforme au high-volume return
premium académique** — mais **il ne franchit PAS la barre pré-enregistrée** :
- **intraday (M1–M30)** : **fee-killed en taker** exactement comme le prior le prédisait
  (net taker ≤ 0 en 1m/5m ; le maker sauve à peine, t<2) ;
- **haut TF (H1–4H)** : le tueur n'est PLUS le mur des frais (les mouvements 4H dépassent les
  12 bps taker A/R → net taker positif) mais la **robustesse/déflation** : Sharpe 0,26 trop
  faible → **DSR 0,05** écrasé par le multiple-testing (480 essais), **t_HAC<3**, **incohérent**
  entre TF adjacents ;
- **D1/W1** : gros chiffres = **artefacts small-sample** (n=20, overlap h=16).

**On ne branche rien** (ni banc gelé §62, ni voix, ni gate LIVE). Rouvrir seulement si : univers
100+ coins (plus de puissance statistique), OU comme UN input parmi d'autres d'un ensemble
multi-signaux (jamais seul), OU frais ≈ 0 (VIP) sur les configs 4H. Une **voix d'ombre
Grok-vision** mesurée (docs/WYCKOFF.md Partie III) reste la seule extension envisageable — jamais
une conviction, toujours net-de-frais + déflaté.
