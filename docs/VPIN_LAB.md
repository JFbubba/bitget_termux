# VPIN_LAB — toxicité du flux (Easley-López de Prado-O'Hara) : mesure & verdict

**Module** : `vpin_lab.py` — banc de MESURE, classé **SAFE** (lecture seule, défaut OFF, aucun
ordre, aucun chemin d'exécution). **Non branché** : aucun gate live n'est câblé ici.

## 1. Ce qu'est VPIN
VPIN (*Volume-synchronized Probability of INformed trading*, Easley/López de Prado/O'Hara,
*Review of Financial Studies* 2012) mesure la **toxicité du flux** vue par un fournisseur de
liquidité :

1. on ré-échantillonne le flux en **buckets de VOLUME ÉGAL** V (pas de temps égal) — le temps
   d'horloge est remplacé par le temps-volume ;
2. dans chaque bucket on classe le volume en acheteur/vendeur (`buy`, `sell`) ;
3. `VPIN = moyenne mobile sur N buckets de |buy − sell| / (buy + sell)`.

Un déséquilibre persistant par unité de volume ⇒ flux probablement **informé** ⇒ **sélection
adverse** pour le maker (nos cotations passives se font « ramasser » juste avant que le prix
parte contre nous). C'est la thèse « fill-and-be-killed » que ce labo teste.

### Substrat de données (réutilise l'existant)
- **buy/sell taker DIRECT** : `taker_flow.volume_delta_series` (endpoint `taker-buy-sell`).
  ⚠️ l'endpoint ne rend que **~30 barres/appel** (vérifié ; cohérent avec la mémoire
  `orderflow_lab` « sous-alimenté »). Il alimente donc le **snapshot `--status`** (VPIN
  courant), PAS le backtest.
- **BVC (Bulk Volume Classification)** sur **bougies** : `buy_fraction = Φ(Δclose / σ(Δclose))`
  via `black_scholes._norm_cdf`, σ roulant causal. C'est le repli **canonique** du VPIN quand
  le buy/sell signé manque (même papier 2012). L'historique `data_history/` (jusqu'à ~30 k
  barres/TF pour BTC/ETH/SOL) rend le test STATISTIQUE faisable.
- **markout post-fill** : `microstructure.markout` réutilisé tel quel (P&L bps du côté du fill
  vu `h` barres plus tard ; négatif = toxique).
- **validation** : `agent_validation.deflated_sharpe/psr/sharpe`, `backtest_brain.walk_forward/pbo`.

## 2. L'expérience (le point du labo)
1. Rejouer des **fills maker post-only** sur bougies (borne SUP, comme `mm_lab`) : fair =
   clôture précédente ; `bid = fair·(1−s/2)`, `ask = fair·(1+s/2)` ; buy rempli si `low ≤ bid`,
   sell si `high ≥ ask`.
2. **Tagger** chaque fill du **VPIN causal** (buckets formés de barres ≤ barre précédente) et
   du **sens du flux** (delta BVC).
3. Mesurer le **markout NET** (net de `FEE_MAKER_RT_BPS`, défaut 4 bps A/R maker ; 8 bps pour
   le spot avec BGB) `h` barres plus tard.
4. **Contraste** : markout moyen du **décile VPIN haut** vs **bas**. Hypothèse toxique ⇒
   `diff = hi − lo < 0` (haut VPIN plus toxique).
5. **Gate** : écarter les fills où VPIN ≥ seuil **ET** le flux est CONTRE notre côté (buy quand
   le flux vend, sell quand le flux achète). Retenu seulement s'il **améliore le markout moyen
   NET** (fills gardés vs tous — coût d'opportunité des fills bénins manqués inclus).

### Validation (honnête)
Non-chevauchant (fills espacés ≥ `h`) · **bootstrap** (2000×) sur la différence hi−bas ·
**Deflated Sharpe** & **PBO** sur la grille · **t déflaté** par le nombre d'essais (comme
`orderflow_watch`). Un gate n'est « robuste » que si : `diff<0` ∧ `|t_défl|≥2.5` ∧ `boot95<0`
∧ gate améliore ∧ `DSR≥0.95`.

### Échelle de timeframes (ERR-001) — et ses limites HONNÊTES
BVC couvre **M1·5m·15m·30m·H1·H4·D1·W1**. Deux limites sont SIGNALÉES, jamais fabriquées :
- le VPIN signé **DIRECT** ne couvre que 5m..1day (l'endpoint n'a **pas de M1**) ;
- le VPIN **W1** est **dégénéré** (trop peu de buckets ⇒ flag `[DÉGÉNÉRÉ W1]`) ; SOL W1 =
  données insuffisantes.

## 3. VERDICT MESURÉ (18/07/2026, BTC/ETH/SOL × échelle TF, 92 essais valides)
**Pas d'amélioration déflation-robuste. La toxicité du markout maker NE se sépare PAS par
VPIN à la résolution disponible.**

- **0/92** essai robuste. **max |t_défl| = 0,47** (seuil 2,5). **max DSR = 0,188** (seuil 0,95).
  **PBO = 0,60** (> 0,5 ⇒ le choix de config est surappris).
- Signe du contraste **INCONSISTANT** et plutôt à l'ENVERS de l'hypothèse : `diff<0` (toxique)
  seulement **34/92** ; `diff>0` (inverse) **58/92**. En intraday (1m..1H, 3 sym), markout net
  moyen VPIN **haut −4,39 bps** vs **bas −6,19 bps** — le haut VPIN est même LÉGÈREMENT MOINS
  mauvais (bruit : boot95 chevauche 0, t_défl ≤ 0,47).
- **Fait structurel** : TOUS les markouts sont **négatifs** (~−4 à −6 bps net en intraday) —
  un fill post-only naïf est systématiquement adverse (il se déclenche quand le prix TRAVERSE
  le niveau), MAIS ce coût est ~**constant à travers les déciles de VPIN** : le VPIN ne dit pas
  quels fills seront toxiques.
- Aux TF D1/W1, les chiffres explosent (±100s de bps) avec n qui s'effondre = **bruit
  petit-échantillon** (le piège déjà noté ; W1 flaggé dégénéré).

### Interprétation (brutalement honnête)
La claim du gate VPIN est DIFFÉRENTE d'un edge directionnel (qualité de fill à coût de frais
quasi nul) — elle méritait son propre test. **Elle échoue** ici, et l'échec est
déflation-robuste POUR LA QUESTION DÉPLOYABLE-AVEC-LES-DONNÉES-DISPONIBLES. Nuance de méthode :
le domaine natif du VPIN est le **temps-volume au niveau TRADE** (Easley-LdP bucketaient
trade-par-trade) ; ici on l'approxime par BVC au niveau BARRE (endpoint direct trop court, et
`orderflow_tape` ne persiste que ~100 prints récents, non historisés). Un test tick-par-tick
exigerait une **persistance de la tape signée** qui n'existe pas dans le dépôt. Le résultat est
donc : *avec les données réellement disponibles, VPIN n'améliore pas la sélection des fills
maker* — cohérent avec le prior « edges orderflow marginaux » sans le confondre avec lui.

## 4. Où un gate live se brancherait PLUS TARD (repérage SEUL — rien câblé)
Si un jour un VPIN tick-level montrait une séparation robuste (à re-mesurer avec tape
persistée), le gate s'insérerait en **veto de cotation**, jamais en logique d'ordre :
- **spot MM** : `market_maker.no_quote_reasons` (≈ `market_maker.py:481`) — ajouter une raison
  `vpin_toxique` qui retire la cotation du côté menacé (le plan devient `None`, aucun fill).
- **futures maker** : `futures_executor._place_maker` (≈ `futures_executor.py:1431`) — n'ouvrir
  en post-only que si VPIN < seuil du côté concerné, sinon rester passif / différer.

Dans les deux cas : opt-in `.env` **défaut OFF** (`VPIN_GATE_ENABLED`), fail-safe (VPIN
indispo/périmé ⇒ gate inactif, jamais de blocage), **murs `guards()` INTOUCHÉS** (le gate ne
peut que RÉDUIRE l'activité, jamais desserrer un cap). **Décision propriétaire requise** — et
seulement APRÈS une mesure tick-level robuste, que ce labo n'a PAS obtenue.

## 5. Reproduire
```bash
python vpin_lab.py --status BTCUSDT 1h     # VPIN courant (direct ~30 barres + BVC bougies)
python vpin_lab.py --run BTCUSDT 1H        # 1 (sym,TF) détaillé
python vpin_lab.py --run-all               # le verdict (BTC/ETH/SOL × échelle TF)
```
Résultats détaillés : `.vpin_lab_result.json` (gitignoré). Tests : `test_vpin_*` dans
`tests_audit.py`. Verdict au registre : `docs/VERDICTS.md`.
