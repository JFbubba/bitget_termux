# FORMATION_LECTURES.md — synthèse de bibliothèque (campagne du 18/07/2026)

Notes de formation demandées par le propriétaire : lecture de ~20 ouvrages (thèse monétaire
Bitcoin, technique blockchain, valorisation crypto, psychologie/risque, AT classique,
microstructure/HFT/FX) **complétée par recherche web approfondie**, le tout lu **à travers la
lentille du bot** : qu'est-ce qui est *actionnable*, *déjà couvert*, *déjà rejeté* (mesuré
net-négatif), ou *à mesurer* — pas des fiches de lecture génériques.

> **Discipline de la maison.** Un apprentissage sans implication actionnable ou sans source
> n'entre pas ici. Tout « candidat » listé est **non testé** — il ne desserre aucun mur, ne
> devient une voix qu'après mesure net-de-frais + Deflated Sharpe (anti sur-testing). Les
> murs (50/250, ×5, stop −5 %, porte d'edge) restent absolus. Le banc reste **gelé à 14**.
>
> **Le fil rouge de toute la campagne** (convergence des 5 clusters ET des mesures internes du
> dépôt) : *le seul levier réellement ouvert n'est pas un nouveau signal directionnel — c'est
> l'EXÉCUTION (maker/frais) et la SÉLECTION d'edge net.* Les grands traders l'appellent
> « survivre d'abord, prédire ensuite » ; la microstructure l'appelle « ne pas être le taker
> naïf ». Même vérité, deux vocabulaires.

---

## 1. Thèse monétaire Bitcoin — conviction d'accumulation (pas un signal)

**Acquis dur (le seul vraiment vérifiable).** La *rareté d'offre protocolaire* (plafond 21 M,
émission décroissante, inélastique à la demande, garantie par le code + le coût PoW) est un
**fait auditable**, pas une prédiction. C'est le socle qui justifie de **détenir** du BTC à
long terme — rien de plus. Ammous (*L'étalon Bitcoin*) formalise via la dureté monétaire
(stock/flux) ; garder l'argument technique, **jeter la certitude idéologique** (l'ouvrage est
largement jugé « propagande informée » : idéalise l'étalon-or, sous-estime les problèmes d'une
monnaie déflationniste — Cato, Alliance for Just Money).

**Fait nouveau 2024-2026 (hors livres, tous antérieurs).** Adoption institutionnelle devenue
*structurelle* : ETF spot US ~107 Md$ collectés en un an (IBIT ~78 Md$), réserve stratégique
US (mars 2025, mais **non financée**, bloquée jan-2026). Valide empiriquement le pari des
livres — MAIS crée une **fragilité** : demande concentrée/à effet de levier (Strategy ~843k BTC,
~97 % des achats corporate nets début 2026 ; un krach a effacé ~62 Md$ de trésoreries). La
demande institutionnelle est un facteur de fragilité autant que de solidité (vendeur forcé
possible).

**Modèles testables — verdicts (honnêtes).**

| Modèle | Verdict | Pourquoi |
|---|---|---|
| **Stock-to-Flow (PlanB)** | **FALSIFIÉ** | Écart massif 2021-23 (>100 k$ prévu, <16 k$ réel), autocorrélation (2 séries tendancielles), ignore la demande. Auteur invalidé publiquement. |
| Cycle de halving | **FRAGILE** | Effet 2024 réel mais ~1/5 de 2020, plus muet, appréciation souvent AVANT le halving → pas un timing. |
| Metcalfe (valeur ∝ n²) | **FRAGILE** (borne haute) | R²~0,95 mais pente ~1,69≠2, relation **spurieuse** (tendances stochastiques communes) une fois instrumentée. |
| Loi de puissance (P∝t^~5,8) | **À MESURER — signal LENT** | Le seul avec dérivation mécaniste + falsifiabilité (Santostasi-Perrenod, R²=0,96 sur 5 696 j) ; MAIS en test réel (2025 rouge). Usage max = z-score de sur/sous-évaluation lent, jamais un levier. |

**Implication bot (accumulation).** Ancrer la conviction sur le **fait vérifiable** (rareté),
**pas** sur un prix cible (S2F FALSIFIÉ = aucun modèle ne fixe d'objectif ni ne justifie de
vendre le cœur BTC). Le **DCA régulier indépendant du prix** est la réponse correcte à la
volatilité ~52 % (vs or ~15 %) et à l'incertitude des modèles ; une année rouge (2025 : BTC ~−8 %,
or +16 %) est *cohérente avec le mandat*, pas un signal de sortie. Au plus : **moduler
l'intensité du DCA** via un signal LENT (loi de puissance/opportunité §44 en z-score), jamais
un timing. « Or numérique » reste une **hypothèse non prouvée** (2025 : BTC risk-on, pas refuge).
Leçon de Popper (Mt. Gox) : le **risque de contrepartie > risque de prix** — cohérent avec la
clé Trade-only/retrait inexistant ; le BTC sur exchange reste une exposition résiduelle à
honorer dans la conviction.

---

## 2. Technique BTC & valorisation on-chain — signaux LENTS (le mur des frais ne s'applique pas)

Point de méthode capital : ces métriques sont daily/hebdo/cycle. À cette cadence (quelques
trades/an), **le mur des frais n'est PLUS le tueur** — le tueur devient **N=3 cycles** +
**rupture structurelle post-ETF** (plusieurs modèles de top réputés — Pi Cycle, Terminal Price —
ont échoué hors-échantillon ce cycle car ETF/institutionnels/règlements internes ont déplacé le
poids explicatif hors chaîne). Substrat commun : le modèle **UTXO** (chaque UTXO porte le prix de
son dernier mouvement) → toutes ces métriques sont une **carte du coût de base agrégé des
détenteurs**, pas du flux d'ordres.

| Métrique | Verdict | Note |
|---|---|---|
| **MVRV-Z score** | **À MESURER — labo lent** | Le mieux étayé (étude Grobys 2026 : Sharpe B&H 0,45 → **1,28**). Aligné avec `accumulation_engine` (déjà long-only). |
| STH Realized Price (coût de base mains courtes) | **À MESURER — filtre régime** | Le membre le plus « rapide » → plus d'observations → t plus honnête. Porte on/off du levier directionnel. |
| CVDD / Realized Price | **À MESURER — confirmation plancher** | Détecteur de creux (p~99 % dans l'étude). Second témoin d'accumulation agressive (dans les murs). |
| NUPL | À MESURER (redondant MVRV-Z → tester l'UN des deux) | Famille identique (realized cap). |
| **NVT ratio, Metcalfe/NVM** | **BRUIT — spurieux prouvé** | Vélocité instable (Burniske MV=PQ), autocorrélation/endogénéité. **Ne pas relancer.** |
| Exchange netflow, ETF flows | **DÉJÀ COUVERT** | modules flux exchange + `market-intel`. |
| HODL waves / CDD / dormancy | **VEILLE** | Dégradés par les reshuffles custodial post-ETF (mouvement Coinbase 70 Md$ a « cassé » les waves sans vente réelle). |

**Frameworks portefeuille (Burniske / Freeman / Cox).** La seule idée réellement nouvelle et
transposable = **sizing modulé par la valorisation on-chain** (DCA/position ∝ z-score d'écart au
coût de base : accumuler plus quand MVRV-Z est bas). Le reste (univers qualité/liquidité,
cœur/satellite, règle de non-ruine) est **déjà incarné** (`universe.py`, murs 50/250, caps par
paliers). Confirme aussi « 3 positions max ne diversifie pas » (core crypto = un seul beta).

**Implication bot.** 3 candidats de labo *lent* (horizon 7-30 j), tous comme **tilt sur un moteur
déjà long-only** (accumulation), jamais comme levier futures ni signal intraday. **N=3 impose de
déflater agressivement** (Deflated Sharpe déjà en place) et de traiter ça comme **beta de cycle,
pas alpha**.

---

## 3. Psychologie, risque & sagesse — 10/12 invariants déjà incarnés

Les grands traders (styles opposés : trend vs contrarian) **convergent** sur un noyau — c'est le
signal que ce sont des invariants, pas des recettes. Mapping au bot :

**Déjà incarné (structurellement) :** risque > méthode (murs `guards()`), couper les pertes (stop
−5 % → kill-switch), risque≠volatilité (vol-targeting GARCH), anti-ancrage/flexibilité
(EARCP révoque les voix sur t-stat, comme Druckenmiller sur les faits), patience/anti-overtrading
(porte d'edge = no-trade par défaut), travail en préparation (labos hors boucle live), marge de
sécurité (Deflated Sharpe + net-de-frais obligatoire), discipline > prédiction (fail-safe, 3
portes). **Le bot est par conception un « market wizard » sur le risque : il ne prédit pas mieux,
il survit parce que les murs sont absolus.**

**Gaps — candidats (non testés) :**

| # | Règle non incarnée | Proposition | Verdict |
|---|---|---|---|
| **A** | Risque par trade en **% du capital** (Kovner 1-2 %), pas en $ fixes | Garde additionnelle **sous** les murs : `distance_SL × taille ≤ 1 % equity`. Aujourd'hui 50 $ sur ~206 USDT = mur en *notional*, pas en *risque encouru*. | **À CODER simple** — l'invariant le plus cité, déterministe, sous les murs. |
| F | Expectancy live par voix/symbole + throttle | Extension `live_ic_audit`/`trade_forensics`, auto-réduction si expectancy réalisée < seuil. | **À CODER** (instrument lecture seule) puis À MESURER (throttle). |
| G | Marge de sécurité *au-dessus des frais* | Porte d'edge `edge_net > k × frais` (k>1) au lieu de `> 0`. | À CODER simple (`k` réglable) — matérialise le coussin de Graham. |
| B | De-risk gradué après pertes consécutives | Diviser le notional après N pertes / à −2,5 % intraday. | À MESURER (peut couper juste avant le rebond). |
| C | Filtre R:R minimal à l'entrée | Rejeter TP/SL ≤ seuil. | À MESURER (risque de redondance avec la porte d'edge nette). |
| E | Pyramiding à la Livermore (ajout sur gagnant) | Scaling-in décroissant, jamais sur perte. | À MESURER — **risque frais élevé**, tester en maker only. |

**Priorité : A** (risque en %) puis **F** (expectancy observable). B/C/E ont une bonne intuition
mais un effet net-de-frais **non acquis** (historique de « bonnes idées » tuées par les frais).

---

## 4. AT classique — déjà absorbée par le banc, fee-killée ailleurs (verdict tranché)

**Déjà dans le banc (rien à rebrancher) :** théorie de Dow, MM/croisements, S/R & canaux
(`technicals.py`: VWAP ancré, volume/TPO profile, clusters de liquidité), volatilité/Bollinger/ATR
(`volatility.py`: GARCH — déjà mesuré > `arch`), structure/figures (voix `structure`, seul agent
séquentiel), volume/OBV (`orderflow`/`flows`). **Ichimoku n'apporte rien** qu'une recombinaison de
MM + S/R déjà présents.

**Chandeliers & figures chartistes — fee-kill confirmé par la littérature :** Marshall 2006
(bootstrap DJIA : chandeliers sans valeur), Chan et al. IEEE 2021 (68 patterns, top-23 cryptos :
« de peu d'utilité », faux signaux), ScienceDirect 2026 (intraday crypto : les rares « tentativement
profitables » **« devraient être exclus du trading réel »**). Data-snooping : Sullivan-Timmermann-White
(aucune règle simple ne survit au Reality Check) ; Park & Irwin 2007 (profits jusqu'aux années 1990
puis érosion). **Bulkowski lui-même** : sur ~14 000 figures, le taux d'échec **monte de 26 % (90s) à
49 % (2003-07)** = edge arbitragé/dégradé — exactement le motif « réel in-sample → non-tradable en
walk-forward » déjà connu du dépôt. Les chiffres brillants de Bulkowski sont **bruts, actions,
positionnel** → non transférables tels quels en crypto intraday net-de-frais.

**Seule piste résiduelle (priorité basse, espérance faible) :** utiliser les **niveaux** dérivés
des figures (swing highs/lows, measured-move) **non comme signal directionnel** mais comme
**contexte d'exécution maker** — des niveaux S/R nets où poser des post-only et calibrer TP/SL,
branché sur le levier *prouvé* (frais), pas sur une prétention d'alpha. Protocole obligatoire :
échelle COMPLÈTE de TF (ERR-001), test holistique séquence figure→cassure→objectif (ERR-002),
walk-forward OOS, benchmark buy-and-hold (ERR-014), lentille maker. **Message net : rien à ajouter
au banc gelé.**

---

## 5. Microstructure / HFT / FX — le cluster le plus actionnable

**Ce que la littérature EXPLIQUE (mécaniquement) de nos mesures :** le maker est un levier de
**FRAIS**, pas d'**alpha**. Phénomène « **fill-and-be-killed** » (arxiv 2502.18625) : un ordre
passif au top-of-book ne se remplit que parce qu'un flux contraire a épuisé la liquidité de ce côté
— i.e. la condition d'un mouvement immédiat CONTRE nous. Mesure brutale : les ordres à rendement
5 s *négatif* remplissent à ~90 %, ceux à rendement *positif* à ~10 % (corrélation **négative**
fill/rendement). → le maker *divise* la perte directionnelle (économie 0,06→0,02 %) mais ne la
bascule PAS positive. **OBI et notre `trade_sign` sont réels mais < frais** (BTC ~0,42 bp @30 s ;
à 4 bps taker A/R toutes les configs sont négatives net) → **pas d'alpha taker, confirmé**.

**La seule vraie piste net-de-frais NOUVELLE du lot :**

- 🟢 **Gate d'exécution VPIN** (toxicité du flux, Easley-López de Prado). VPIN = probabilité de flux
  informé par *buckets de volume* — **ne nécessite PAS le MBO** (seulement les trades + sens
  agrégé, **disponibles chez Bitget** via l'endpoint Taker-Buy-Sell, capacité non exploitée n°1).
  Usage : **ne pas poster de maker (ou élargir/annuler) quand VPIN est élevé contre notre pose** →
  réduit l'adverse selection *sans coûter de frais*. **[À CODER exécution — prototype labo
  `vpin_gate`, validé Deflated Sharpe, mesuré sur `trade_forensics`.]** C'est un **gate de qualité
  de fill**, pas une voix directionnelle.

**Enrichissements d'exécution (à mesurer) :** queue position (front-of-queue ~13× moins d'adverse
selection → poster tôt, raffiner `FUTURES_MAKER_WAIT_S=12` en *cancel-on-adverse-imbalance* plutôt
qu'un timeout aveugle) ; choix du côté de pose selon fill vs toxicité.

**Carry & macro (Lien).** Le carry FX = le funding perp (long spot/short perp encaisse le funding
delta-neutre ; se dénoue violemment en risk-off). **Déjà fait** (`carry_auto`). Enrichissements :
**kill risk-off du carry** (couper/réduire quand le funding s'inverse brutalement ou DXY pique) ;
**sizing par session** (US ~13:00 UTC haute-vol vs creux asiatique ; éviter de poster juste avant
une borne de funding 8 h). DXY↔BTC ~−0,4 à −0,8 mais **de régime (mensuel), pas intraday** → filtre
de contexte/black-out (déjà Kalshi §59), pas un signal court. **[À MESURER, jamais un signal isolé
→ Deflated Sharpe.]**

**Méta Flash Boys (pour un bot retail).** On ne gagnera jamais la course à la vitesse (285 ms
Francfort→Bitget = **non-enjeu à l'horizon minute**, confirmé) → l'edge vient de l'**horizon + la
minimisation des frais**, jamais de la latence. **Ne pas être le taker naïf** : un fill instantané
est *suspect* (adverse selection). **Le speed bump du pauvre = la patience** (post-only patient,
annulation sur imbalance adverse). Découpe/iceberg = N/A à 10-25 USDT (impact négligeable, déjà
invisible dans le bruit) — à ré-évaluer seulement au-dessus de plusieurs milliers d'USDT.

---

## 6. Backlog consolidé « à mesurer / à coder » (non testé — décision propriétaire)

Classé par rapport valeur/effort. **Aucun n'est branché** ; chacun = un labo de mesure d'abord.

1. **Garde risque-en-% du capital** (§3-A) — *à coder simple*, garde déterministe sous les murs,
   l'invariant de risque le plus universel. Le meilleur rapport valeur/effort.
2. **Gate d'exécution VPIN** (§5) — *prototype labo* ; seule piste net-de-frais réellement nouvelle,
   améliore la qualité des fills maker sans frais, faisable sans MBO.
3. **MVRV-Z comme porte/multiplicateur du DCA** (§2) — *labo lent* ; frais négligeables à cette
   cadence, aligné avec l'accumulation ; déflater fort (N=3 = beta de cycle).
4. **Expectancy live observable + marge de sécurité `k×frais`** (§3-F/G) — *instrument lecture
   seule* puis throttle ; rend l'invariant « risque > méthode » observable en continu.
5. **Kill risk-off du carry + sizing par session** (§5) — *à mesurer* ; enrichit `carry_auto`.
6. **Deux réglages du funding-arb natif Bitget** (Academy) : porte **basis-rate d'entrée** +
   **batch-splitting** des jambes de carry — concrets, absents de notre carry taker.
7. **Vote d'ombre « positioning elite traders »** (API Copy/Elite) — *labo IC* ; copier est
   fee-killed (10 % profit-share), mais le biais net long/short agrégé filtré est un feed gratuit à
   mesurer comme ombre (façon `news_shadow`). Vérifier la lisibilité des positions via l'API.

**Priorité basse / veille :** niveaux de figures comme contexte d'exécution (§4, espérance faible) ;
PoolX net-en-USDT vs Earn (risque token) ; de-risk gradué / R:R filter / pyramiding (§3-B/C/E,
effet non acquis).

---

## 7. Checklist d'anti-patterns pour l'agent de recherche (à m'appliquer)

Chaque biais de trader humain a son équivalent dans ma méthodo. Avant de déclarer un edge :

- **Sélection in-sample = t gonflé** → seul le **walk-forward OOS** donne le t honnête.
- **Multiple testing** → Deflated Sharpe / seuil √(2 ln N) ([[labo-hac-dsr-instruments]]).
- **Test de nullité** (shuffle/permutation/bootstrap) avant de croire un signal.
- **Chercher la réfutation**, pas la confirmation (vérification adversariale par défaut).
- **Toujours net-de-frais** — un edge brut n'est PAS un edge (~6 bps/côté ≈ 50 % du brut).
- **Look-ahead / contemporain** → lag des features, pas de fuite du futur.
- **Daily-pas-intraday**, **micro-cap/illiquide** = mirages.
- **Échelle de TF complète** (ERR-001) ; **système séquentiel = machine à états** (ERR-014/002).
- **Un seul bloc de marché ≠ edge** ([[geometric-mirage-24h]]) ; l'EWMA institutionnalise la recency.
- **Benchmark buy-and-hold** systématique (distinguer alpha/beta, ERR-014).
- **Disposition effect de recherche** : tuer vite les hypothèses perdantes, ne pas s'accrocher par
  sunk cost ; **anti-gold-plating** (KISS, [[cadrage-livrable]]) ; **VERDICTS.md avant de re-tester**.

---

## 8. Fouille arXiv (18/07/2026) — trading & cryptomonnaies

Deux balayages alphaXiv (microstructure/exécution ; prédictibilité/méthodo) → ~25 papiers. Les plus
pertinents, verdict net-de-frais. **Aucun n'apporte de nouveau signal directionnel net-de-frais** —
tous confirment la thèse du dépôt (frais + exécution = seuls leviers).

**Deep-read (2 papiers) :**

- **« The Quarter-Hour Effect »** (2607.09426, juil-2026) — bursts algo périodiques aux marques
  d'horloge (min 0/15/30/45) sur 6 perp Binance ; prévisibilité OOS réelle mais edge **~0,5 bps
  brut/trade** (les auteurs chiffrent le brut et **refusent** le net : « small relative to trading
  costs ») vs 4 bps A/R maker → **[TUÉ PAR FRAIS comme signal]** (famille OBI/`trade_sign`). **Seul
  apport = TIMING D'EXÉCUTION** : l'adverse selection n'est pas uniforme dans le temps — éviter les
  ordres marketables sur les **10 s d'ouverture de quart d'heure** et moduler l'agressivité maker
  autour. **[Mini-labo d'exécution — À MESURER, léger, défaut OFF]** (complète `market_maker.py`).
- **« AutoQuant »** (2512.22476, déc-2025) — framework de validation *execution-constrained* sur 4
  perp. « does not generate new trading rules ». Résultat net ≈ **zéro/négatif** (Sharpe long ≈ 0,
  **PBO = 0,586**, buy-and-hold **bat** les configs tunées post-ETF ; retirer slippage+funding gonfle
  le CAGR de **+58 %**, tout retirer +92 %). **[MÉTHODOLOGIE à adopter]** : (1) **CSCV/PBO** en
  complément de notre Deflated Sharpe (PBO montre que la DSR seule sous-estime le risque de
  surajustement) ; (2) **grille de stress de coûts** (taker ∈ {3,4,6} bps × funding ∈ {0,5;1;1,5})
  comme *critère de survie*, pas un point unique ; (3) **invariants comptables décomposés**
  backtest↔replay↔exécution par composante (fee/slip/fund/pnl) ; (4) discipline **fenêtre de
  screening ≠ OOS pur**. Fait notable : leurs guards ATR 1-15 min **n'améliorent RIEN net de frais**
  (confirme [[exit-calibration-verdict]]).

**Autres papiers repérés (verdict de survol) :**

| arXiv | Sujet | Verdict bot |
|---|---|---|
| 2502.18625 (Oxford/Turing) | Market Maker's Dilemma (fill-and-be-killed) | **Fondation** — déjà cité §5 (explique maker = frais, pas alpha). |
| 2411.06327 (NTU) | On-chain flows intraday (ETH net inflow prédit ETH) | **À MESURER** (intraday on-chain — vérifier net-de-frais ; prior : bruité). |
| 2606.01650 | Post-Selection Estimation of Sharpe Ratios | **MÉTHODO** — corrige le Sharpe du max-in-sample (= notre piège « sélection gonfle le t »). |
| 2602.00080 / 2603.09219 | GT-Score / AlgoXpert IS-WFA-OOS anti-overfitting | **MÉTHODO** — recoupe DSR + WF ; AlgoXpert = protocole OOS rigoureux. |
| 2605.06405 / 2605.05089 | Funding-aware MM / spot-perp basis collateral control | **VEILLE carry** — cadres pour `carry_auto` (funding comme état stochastique). |
| 2606.00071 | Bitcoin Price Prediction (méta-revue peer-review) | **CONFIRME REJETÉ** — « aucun modèle ne bat le naïf » (DL de prix). |
| 2604.26747 / 2605.24564 | LLM agents contraints / look-ahead bias LLM en backtest | **MÉTHODO voix LLM** — discipline anti-recherche incontrôlée + anti-look-ahead. |

**Net arXiv :** rien à brancher en signal ; **1 mini-labo d'exécution** (timing clock-time) + **3-4
pièces de méthodo** (PBO/CSCV, stress-coûts, invariants décomposés, post-selection Sharpe) à ajouter
à l'instrumentation de validation. Renforce [[labo-hac-dsr-instruments]] et
[[deep-research-new-edges-verdict]].

---

### Sources
Détail des URLs dans les rapports d'agents de la campagne (transcripts de session). Ancres clés :
S2F falsifié (Protos, CryptoSlate) ; ETF 107 Md$ (DL News) ; Grobys 2026 MVRV-Z (osuva.uwasa.fi) ;
échec des indicateurs de top (Bitcoin Magazine) ; fill-and-be-killed & queue (arXiv 2502.18625) ;
VPIN (VisualHFT, López de Prado) ; Bulkowski décroissance OOS (thepatternsite id84) ;
Sullivan-Timmermann-White & Park-Irwin (SSRN) ; Marshall 2006 / Chan 2021 chandeliers ;
Market Wizards (Schwager) ; carry delta-neutre & sessions (Lien).
