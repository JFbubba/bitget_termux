# WYCKOFF.md — méthode de Wyckoff : maîtrise + verdict net-de-frais + design de labo

Référence de formation (campagne 19/07/2026, 3 agents : maîtrise · edge/automatisation · repos).
But : (1) **reconnaître** chaque événement de Wyckoff sur un graphique, (2) savoir **honnêtement**
ce qui est *tradable net-de-frais* vs *narratif non falsifiable*, (3) le **design du seul labo** qui
mérite d'être mesuré. Discipline maison : mesure-d'abord, murs intacts, banc gelé §62.

---

## PARTIE I — MAÎTRISE DE LA MÉTHODE

### 1. Composite Man & 3 lois
- **Composite Man / Operator** : lire le marché « comme si tout était l'œuvre d'un seul gros
  opérateur » ; se positionner *avec* l'argent intelligent en lisant ses traces prix/volume.
- **Loi 1 — Offre & Demande** : demande>offre → hausse. Donne la **direction**.
- **Loi 2 — Cause & Effet** : une *cause* (largeur horizontale du range, comptée en P&F) précède un
  *effet* proportionnel (ampleur de la tendance). Donne les **objectifs de prix** (§6).
- **Loi 3 — Effort vs Résultat** : volume (effort) vs amplitude/écart (résultat). **Divergence** =
  alerte de retournement (ex. gros volume + petit écart = absorption).

### 2. Cycle de prix : Accumulation → Markup → Distribution → Markdown.

### 3. Schéma d'ACCUMULATION (range borné : support=SC, résistance=AR ; 5 phases A→E)
⚠️ **Deux variantes canoniques** (StockCharts) : #1 **avec** Spring, #2 **sans** (résolution directe par SOS). **Le Spring n'est PAS obligatoire.**

| Événement | Phase | Signature prix/volume | Action |
|---|---|---|---|
| **PS** Preliminary Support | A | écart s'élargit, volume ↑, le prix ralentit | observer, début du range |
| **SC** Selling Climax | A | **volume extrême**, écart large, **clôture au-dessus du bas** (pros achètent) → définit le support | ne pas acheter le couteau |
| **AR** Automatic Rally | A | rebond vif, volume ↓ → définit la résistance | marque le plafond |
| **ST** Secondary Test | A/B | re-test du SC à **volume/écart réduits**, plus-bas ≥ | confirme la fin de baisse |
| **UA** Upthrust Action | B | faux plus-haut mineur testant l'offre en haut | range pas mûr |
| **Creek** | B-D | résistance-zone sinueuse (sommets de rallyes) | mur à franchir (JAC) |
| **Spring / Shakeout** | C | **fausse cassure sous le support** puis rejet ; idéalement **volume faible** (peu d'offre) | cœur du setup |
| **Test** (du spring) | C | re-descente à **volume faible**, plus-bas plus haut, pas d'acceptation sous le support | **déclencheur d'entrée** ; stop < bas du spring |
| **SOS** Sign of Strength | C-D | avance **écart large + volume ↑**, nouveaux plus-hauts | confirme le spring ; entrée breakout |
| **JAC** Jump Across the Creek | D | franchit la résistance, volume en expansion | événement de zone, pas un niveau exact |
| **LPS** Last Point of Support | D | pullback à **écart/volume réduits**, plus-bas plus hauts (plusieurs possibles) | **meilleure entrée** ; ligne de comptage P&F |
| **BU** Back-Up to the Creek | D | repli faible-volume qui **tient au-dessus de l'ex-résistance** | entrée la plus fiable ; stop < BU |

### 4. Schéma de DISTRIBUTION (miroir, au sommet ; UTAD non obligatoire)

| Événement | Phase | Signature | Action |
|---|---|---|---|
| **PSY** Preliminary Supply | A | volume élargi, la hausse ralentit | observer |
| **BC** Buying Climax | A | **volume marqué**, écart large, clôture loin du haut → définit la résistance | ne pas chasser |
| **AR** Automatic Reaction | A | baisse vive → définit le support | plancher du range |
| **ST** Secondary Test | A/B | re-test du BC à volume/écart réduits | confirme le plafond |
| **UT** Upthrust | B/C | **fausse cassure au-dessus** puis retour (bull trap) | short possible sur rejet |
| **UTAD** Upthrust After Distribution | C | test final de la demande : cassure des plus-hauts puis **rejet net** | **setup short** ; stop > plus-haut UTAD |
| **SOW** Sign of Weakness | B-D | baisse à **écart/volume accrus** vers/sous le support | bascule baissière |
| **ICE / Fall through the Ice** | D-E | support-ligne sous le range ; cassure puis retest par-dessous qui échoue | déclencheur baissier |
| **LPSY** Last Point of Supply | D | **rallye faible** (écart étroit, plus-hauts plus bas ; plusieurs possibles) | entrée/renfort short ; stop > LPSY |

### 5. Types de Spring / Upthrust — ⚠️ se fier à la SIGNATURE, pas au numéro
La **numérotation #1/#2/#3 est INVERSÉE entre sources** (Evans/Pruden autoritatif : #1=le plus profond/gros volume=prudence ; retail/crypto : souvent l'inverse). **Le fond est constant** :
- **Profond + gros volume + offre sort** → vendeurs pas finis → **prudence**, attendre test(s).
- **Superficiel + faible volume + pas d'offre** → épuisement → **achat immédiat** (stop sous le bas).
Idem upthrusts en miroir (⚠️ un « vrai breakout haussier à gros volume » n'est PAS de la distribution — ne pas shorter).

### 6. Comptage P&F (loi Cause & Effet)
`Objectif = (nb colonnes à la ligne de comptage) × box_size × reversal(=3)`, ajouté à 3 références
(ligne de comptage = max, bas du range = min, milieu = intermédiaire). Ligne de comptage au **LPS**
(accum) / **LPSY** (distrib). Compter **de droite à gauche** ; segmenter les grands comptes. Les
cibles sont des **zones « stop-look-listen »**, jamais des points exacts.

### 7. 9 tests, VSA, validation
- **9 tests d'achat/vente** = checklist binaire de maturité du range (objectif P&F atteint, PS/SC/ST présents, volume ↑ sur rallyes / ↓ sur réactions, tendance cassée, plus-bas/hauts plus hauts, force relative, base formée, **potentiel ≥ 3× le risque** — seul le ratio 3:1 est d'origine Wyckoff).
- **VSA** (Tom Williams) = quantification barre-à-barre de effort/résultat : **No Supply** (petite barre baissière faible-volume=long), **No Demand** (petite barre haussière faible-volume=short), **stopping volume**, **shakeout**. Recoupe directement SC/BC/spring/UT.
- **Validation Spring** : borne inférieure claire + échec d'acceptation sous le support + Test à volume plus faible + SOS ensuite. **Invalide** si acceptation/construction sous l'ex-support. (Seuils chiffrés retail type « volume test < 80 % du spring » = heuristiques à **re-mesurer**, hors textes primaires.)

Sources détaillées : StockCharts ChartSchool (Wyckoff Method, Laws, Jumping the Creek, PnF),
Hank Pruden *Three Skills of Top Trading*, Villahermosa *tradingwyckoff.com*, financial-spread-betting
(springs/upthrusts), VSA (Tom Williams/TradeGuider). URLs dans les transcripts de la campagne.

---

## PARTIE II — VERDICT HONNÊTE (tradable net-de-frais ? automatisable ?)

**Wyckoff en tant que méthode (lecture discrétionnaire de phases) = MÊME PIÈGE que SMC/ICT (déjà
rejetés, [[adm-dmi-adx-rejected]]/ERR-014).** Cadre narratif riche, mais :
- **Aucun backtest propre n'existe** (QuantifiedStrategies : méthode « manque de règles », « très
  difficile à backtester »). Data-snooping non corrigé (Sullivan-Timmermann-White ; Park-Irwin).
- **Look-ahead intrinsèque** : un *spring* n'est un spring qu'*après* le test réussi ; un *UTAD*
  qu'après l'échec de la cassure. Mettre la confirmation dans la règle = tricher sur le futur.
- **Labellisation de phase discrétionnaire** (2 analystes ≠), dépendante du contexte (circularité),
  multiple-testing massif (dizaines d'événements × 8 TF × seuils).
- **Preuve directe négative** : étude de falsification (arXiv 2605.04004) — momentum sur pic de
  volume + exhaustion sur assèchement (= logique climax/spring) parmi 14 familles OHLCV, walk-forward
  + friction → **les 14 échouent** net-de-coûts (contrôles positifs survivent t=5,8 → le harnais sait
  détecter un vrai edge).

**La SEULE nuance juste** : Wyckoff met le **VOLUME au centre** (vs SMC/ICT price-only), et le
**volume anormal a une signature académique réelle** — high-volume return premium (Gervais-Kaniel-
Mingelgrin 2001), overréaction crypto post-choc (Caporale-Plastun 2020). Donc **un sous-ensemble
d'événements est objectivement définissable AU CLOSE, sans look-ahead** : les **climax de volume**
(SC/BC) et le **spring intrabar** (bougie qui casse un plus-bas et referme au-dessus). C'est le seul
angle mesurable. Le reste (phases, composite man, springs/UTAD *confirmés*) = non falsifiable → **ne
rien brancher au banc gelé §62**.

**Prior honnête** : même les climax objectifs finiront **probablement fee-killed en taker** (frais
≈6 bps/côté = le tueur) ; seule chance = **maker + horizon long sur BTC/ETH**. À mesurer, pas à croire.

---

## PARTIE III — AUTOMATISATION & OUTILS

- **Repos clonés** (`/root/repos_utiles/`, usage interne) : `xai-org/xai-sdk-python` (Apache-2.0,
  API+vision Grok), `keithorange/PatternPy` (détection déterministe OHLCV, léger), `white07S/Trading
  PatternScanner` (+ débruitage Kalman/Savitzky-Golay des pivots). **Écartés** : grok-1 (300 Go),
  détecteurs vision YOLO (AGPL + redondants avec Grok), `stock-pattern` (GPL contaminant).
- **Grok-vision** (« Grok lit le chart pour repérer Wyckoff ») : techniquement trivial (SDK ou
  endpoint OpenAI-compat `api.x.ai/v1` ; `grok-4.1-fast` ~**<0,01 $/chart**), MAIS **LLM cloud →
  non-déterministe + hallucine** sur la lecture fine → **uniquement une voix d'OMBRE opt-in MESURÉE**
  (moule `llm_agent.py`, gated, fail-safe), jamais dans le banc, jamais desserrer un mur. On mesure
  « l'avis de Grok a-t-il une IC nette de frais ? », on ne « fait pas trader Grok ». Nécessite une
  **clé xAI payante** (à ranger en `.env`).

---

## PARTIE IV — DESIGN DU LABO (le seul honnête)

**`wyckoff_lab.py`** (à construire, SAFE, défaut OFF, lecture seule, esprit `grid_lab`/`vpin_lab`) —
mesurer si un **climax de volume objectif** (proxy SC/BC, **look-ahead-free**) porte un rendement
forward net-de-frais, avec barre anti-sur-testing.

- **Événement (100 % connu au close)** : `vol_z=(vol−mean(vol,N))/std(vol,N) ≥ 3` ; range large
  (percentile ≥90) ; contexte = nouveau plus-bas/haut N-barres ; **close-location** `CLV=(close−low)/
  (high−low)` (SC→CLV≥0,6 long ; BC→CLV≤0,4 short). Variante **spring intrabar** : `low<min(low,M)` **et**
  `close>min(low,M)`.
- **Entrée** open t+1 ; **mesure** rendement forward net-de-frais à h∈{1,2,4,8,16}, **taker ET maker**.
- **Échelle TF COMPLÈTE** (ERR-001) ; **univers liquide** (exclure alts illiquides, la VSA y casse).
- **Validation** : t **HAC/Newey-West** + **Deflated Sharpe** (sur tous les essais) + **walk-forward
  OOS** (sélection seuils en OOS uniquement) + **shuffle/permutation** (l'edge doit s'effondrer) +
  **contrôle positif** (réversion 1h connue doit survivre) + **benchmark buy-and-hold** (alpha vs beta,
  ERR-014). Réutilise `audit_core` (HAC/DSR [[labo-hac-dsr-instruments]]), `candles_history`, la
  lentille frais [[exec-fees-lever]].
- **Critère de succès pré-enregistré** : forward-R net > 0 OOS, **t_HAC ≥ 3**, **DSR ≥ 0,95**, cohérent
  ≥2 TF adjacents, > B&H market-neutral. Sinon → **réel-non-tradable** dans `VERDICTS.md`, on ne branche rien.
- **NE PAS mesurer** (look-ahead) : spring « confirmé par test », phases labellisées, tout signal
  exigeant l'avenir.

**Résumé** : on maîtrise Wyckoff (Partie I), on sait que ce n'est pas un edge tradable en l'état
(Partie II), et si on creuse c'est **un seul labo de climax de volume** (Partie IV) + éventuellement
une **voix d'ombre Grok-vision** mesurée — jamais une conviction, toujours net-de-frais + déflaté.
