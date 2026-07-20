# BITGET_REFERENCE.md — référentiel Bitget (frais, API, WebSocket, écosystème IA)

Référentiel **durable** des faits Bitget qui conditionnent les décisions du bot. But : arrêter
de raisonner sur des hypothèses/mémoire et s'appuyer sur les sources **autoritatives**.

> ⚠️ **Discipline de source.** **CORRECTION 18/07/2026 (soir)** : `bitget.com` **n'est plus
> systématiquement 403 au WebFetch** — support, academy et blog sont désormais **fetchables**
> (campagne de balayage §formation-lectures, cf. `docs/FORMATION_LECTURES.md`). Réserves qui
> demeurent : (a) certains liens d'articles **404** (liens morts), (b) les pages academy/blog sont
> **marketing** et **cachent presque tous les seuils chiffrés** (funding minimum, basis-rate, APY),
> (c) le fil FR du blog s'arrête ~déc. 2025 → le récent 2026 se lit via les sections d'annonces
> `/support/sections/...` et le **changelog UTA** `/api-doc/uta/changelog` (le changelog V2 legacy
> s'arrête à jan-2026). **La source AUTORITATIVE des faits chiffrés (frais, specs de contrat, tiers)
> reste l'API réelle** (clé Trade-only, lecture) — un endpoint documenté n'est actionnable qu'une
> fois **testé avec notre clé**. Le SDK mirroré (`github.com/tiagosiebler/bitget-api`) reste utile.
>
> Dernière mise à jour : **18/07/2026** (soir — §6 ajoutée).

---

## 1. Frais & déduction BGB (autoritative)

| Marché | Maker | Taker | Déduction BGB (−20 %) |
|---|---|---|---|
| **Spot** | 0,10 % | 0,10 % | ✅ **→ 0,08 %** — BGB dans le **wallet spot** + toggle spot ON |
| **Marge croisée** (spot margin) | 0,10 % | 0,10 % | ✅ **→ 0,08 %** — BGB dans le **compte MARGE CROISÉE** + toggle marge ON |
| **USDT-M perp** | 0,02 % | 0,06 % | ❌ **ne s'applique PAS aux futures** (prévu « à venir », pas live) |
| **COIN-M** | ~0,02 % | ~0,06 % | ❌ (à confirmer contre l'API) |

- **BGB = SPOT + MARGE CROISÉE (spot margin), −20 % — PAS le futures.** ⚠️ CORRIGÉ 19/07 (l'ancienne
  note « SPOT UNIQUEMENT » était INCOMPLÈTE). Deux réglages **SÉPARÉS**, chacun avec SON wallet :
  - **Spot** : toggle « payer les frais en BGB » (`GET /api/v2/spot/account/deduct-info`) + BGB dans
    le **wallet spot**. C'est ce que lit `fee_rates.py`.
  - **Marge croisée** (spot margin, ex. les jambes `alt_carry` en `crossed`) : activer
    **« Margin > VIP > Activate BGB Fee Discount 20 % »** (app : Profile > Trading > Use BGB to Offset
    Fees) **+ transférer les BGB dans le compte marge croisée**. Politique Bitget du **06/06/2024** : la
    déduction s'est DÉPLACÉE du compte spot-margin vers le **compte cross-margin**. Solde BGB insuffisant
    → frais payés en coin. Les BGB en marge croisée servent UNIQUEMENT aux frais (PAS comptés comme
    marge ni dans le risk-ratio). `fee_rates.py` ne lit PAS encore ce toggle marge (angle mort).
  - **Futures** : aucune remise BGB (Bitget prévoit de l'introduire, pas encore live). Le levier
    futures reste le **maker** (0,06 → 0,02).
- **VIP** : chaque +50k USDT de volume 30j baisse les deux côtés (spot ET futures) ; atteignable
  aussi par solde d'actifs ou holdings BGB (mécanisme distinct de la déduction).
- **Empilement** BGB + VIP + parrainage → jusqu'à ~−65 % (spot ~0,04–0,05 % all-in).

**Implication bot (net de frais).** Côté **spot**, la barre = ~0,08 %/côté (0,16 % aller-retour)
au lieu de 0,10 %. Côté **futures**, **pas de remise BGB** : 0,06 % taker / 0,02 % maker restent
le taux réel. → Le levier **maker** (futures 0,06 → 0,02, −67 %) est bien plus fort que BGB pour
le **directionnel** ; BGB allège le **spot** (accumulation, listing-hype, MM) **et la marge croisée**
(jambes `alt_carry` en `crossed`, si BGB dans le compte marge croisée + toggle marge ON) — pas le futures.
Cohérence à faire : `listing_hype` (spot) devrait modéliser 0,08 %, pas 6 bps pleins.

### 1b. Source AUTORITATIVE des frais = l'API (PAS le scraping) — règle proprio 18/07

`bitget.com/fee` **403 au WebFetch** et le proprio **interdit le scraping**. → Les frais se lisent par
**`GET /api/v2/common/trade-rate`** (signé, `businessType` ∈ {`spot`, `mix`}) qui renvoie **MES taux
RÉELS** (VIP + BGB déjà appliqués). **Vérifié live 18/07** (compte du bot, tier de base) :

| businessType | makerFeeRate | takerFeeRate |
|---|---|---|
| `spot` | `0.001` = **0,10 %** | `0.001` = **0,10 %** |
| `mix` (USDT-M) | `0.0002` = **0,02 %** | `0.0006` = **0,06 %** |

→ **Confirme exactement le modèle du bot** (donc les edges « mangés par les frais » le sont *à juste
titre*, pas par excès de sévérité). **Helper central câblé le 19/07** : `fee_rates.py` (LECTURE SEULE,
SAFE, cache TTL, fail-safe -> défauts en dur) `fetch` `trade-rate` et expose `spot_fee_bps()` /
`futures_fee_bps()` ; ses consommateurs recâblés = `market_maker` (plancher spread = 2×fee+buffer),
`listing_hype` (spot), `exit_calibration` (A/R futures). Le taker futures 0,06 % (round-trip 0,12 %)
est appliqué par les **modules d'exécution / labo** (pas une constante d'un module de market-data :
`taker_flow.py` est un lecteur PUR de flux, il n'a **aucune** constante de frais). `carry` ≈ 0,20 %
A/R (2 jambes spot). **Reco RÉALISÉE** : centraliser le *fetch* du taux plutôt que le hardcoder
(auto-ajuste VIP/BGB si le compte monte de tier).

**Matrice d'application (par possibilité)** :
- **Spot** (accumulation, listing-hype, MM spot) : 0,10 %/côté ; **−20 % BGB → 0,08 %** si option BGB ON.
- **Futures directionnel** : entrée+sortie. Maker/maker = 0,04 % A/R ; maker+taker = 0,08 % ; taker/taker = 0,12 %. **BGB ne s'applique PAS.**
- **Carry** (spot+perp) : ~0,20 % A/R (jambes spot dominent).
- **VIP** : baisse les deux côtés par paliers (50k$ vol/30j, ou solde, ou BGB) ; **pas de rebate maker à notre tier** (maker reste +0,02 %). Refetch `trade-rate` pour le taux courant si le volume monte.

## 2. Capacités API v2 (via SDK officiel)

> 📖 **Catalogue EXHAUSTIF des 413 endpoints** (236 v2 + 177 v3 — verbe, auth, type de params, marqueur
> câblé, drapeaux ⚙️ exécution / ⛔ retrait) : [`BITGET_API_CATALOG.md`](BITGET_API_CATALOG.md), généré
> depuis le SDK officiel. Le bot en câble **~23** (≈5 %). **Caveat vérifié 18/07** : le SDK peut lister un
> chemin **absent de l'API réelle** (ex. `mix/market/long-short-ratio` → **404**) — tout endpoint est
> vérifié **contre l'API live** (clé Trade-only, lecture) avant tout usage.

- **Produits** : spot · USDT-M · COIN-M · marge isolée/croisée (emprunt/remboursement) · Earn
  (savings, elite yields, sharkfin, loans) · copy trading. Le compte **UTA** (unifié) existe côté
  API mais le bot **reste en compte classique** (décision — cloisonnement du risque).
- **Types d'ordres** : market, limit, **post-only**, plan (trigger), **TPSL**, batch (lot),
  **modify mid-flight**, **reversal** (flip de position en 1 ordre), **flash-close**.
- **Market data** : OHLCV · orderbook (**merge-depth ≤50 ET carnet complet**) · **taker buy/sell
  volume** (endpoint dédié) · **long/short ratio + account L/S distribution** · **fund flow /
  whale net flow / net inflow** · funding courant+historique · interest rate · open interest
  (contrat + par symbole) · position tiers · index components.

### 2b. Capacités NON exploitées par le bot (candidates — À MESURER avant tout branchement)

| Capacité API | Statut bot | Intérêt / verdict |
|---|---|---|
| **Taker buy/sell volume REST** (`apidata/Taker-Buy-Sell`, 1 req/s) | **NON utilisé** | ⭐ **Volume Delta aligné-période, TOUS symboles, SANS persister la tape WS** (qui ne couvre que 3 symboles). Meilleur chemin que la tape. À tester + mesurer IC net de frais. |
| Carnet **complet** (>15 niveaux) | merge-depth ≤50 / WS books15 | DOM/heatmap plus profonds — gain marginal (déjà 50 niv. en REST). |
| **Fund flow / whale net flow / net inflow** | non confirmé utilisé | flux exogène — mesurer IC net de frais (prudence : probable bruit intraday). |
| Long/short **account ratio** | PARTIEL (`derivs.account-long-short` déjà) | déjà couvert. |
| **Reversal / flash-close** | NON utilisé | **exécution** (flip/clôture en 1 ordre) — piste frais, pas signal. |
| **Flux de liquidations public** (`v3/market/liquidations`) | **DISPONIBLE (v3)** — ✅ vérifié live 18/07 | 🔎 **correction** de l'ancien « inexistant » : le feed EXISTE (public, sans clé) — événements réels `{symbol, side, price, amount, ts}`. Substitut GRATUIT au flux payant type Coinglass. À MESURER (signal contrarien connu mais bruité). |
| **Position long/short ratio** (`mix/market/position-long-short`) | NON utilisé — ✅ live | crowd-positioning par POSITIONS (≠ comptes). Public. Mesurer IC net de frais. |
| **Next funding time** (`mix/market/funding-time`) | NON utilisé — ✅ live | prochain funding + période (8 h) — timing d'entrée/sortie carry autour du settlement. |
| **Spot net-flow série** (`v3/market/spot-net-flow`) | NON utilisé — ✅ live | flux net spot par période (complète `bitget_flows.py`). |

> **MàJ 18/07 — capacités désormais CÂBLÉES en MESURE** (lecture seule, `bitget_market_extras.py`,
> vérifiées live, **NON branchées au banc gelé** sans preuve d'IC nette) : liquidations v3, long/short ×3
> (actif taker / positions / comptes), volume-delta actif (`futures-active-buy-sell`), next-funding, config
> contrat (min-sizes → **filtre de faisabilité** futures). Le module `bitget_flows.py` câble déjà spot
> fund-flow/whale-net-flow. Restent candidats **non câblés** : `v3/market/spot-net-flow`, carnet complet
> (>50 niv.), reversal/flash-close (exécution — via modules bornés uniquement).

## 3. WebSocket

- Endpoint public : `wss://ws.bitget.com/v2/ws/public` (le bot l'utilise via `book_collector.py` :
  canaux **books15** + **trade**, sur **3 symboles** BTC/ETH/SOL).
- **Limites** : 240 souscriptions/h/connexion · ≤1000 canaux/connexion · ≤10 msg/s · ping toutes
  les 30 s (déconnexion si aucun ping pendant 2 min) · market channel màj 300–400 ms.
- Canaux publics : ticker · candle · **trade** (tape) · **books / books15** (profondeur) ;
  privés (order/position temps réel) via clé.

## 4. Écosystème IA Bitget 2026 (veille — RIEN à brancher)

- **GetAgent** : assistant IA (signaux temps réel, sentiment, suggestions de stratégie,
  **exécution conversationnelle** spot/futures/on-chain ; alertes RSI/renversement).
- **GetAgent Playbook** (juin 2026) : plateforme end-to-end de stratégies IA — créer/backtester/
  déployer/héberger **en langage naturel** + **« Trade Harness » standards** + marketplace.
- **GetAgent AI Briefing** (17/07/2026) : brief quotidien IA crypto + actions US.
- **GetClaw** : autre outil IA. Écosystème : 1 M+ users, ~1,2 Md$ de volume « AI agent » (mai 2026).

**Implication bot.** Notre bot est **self-hosted, déterministe, murs durs** — on ne **délègue PAS**
le compte à GetAgent (boîte noire, exécution externe : contraire à la constitution). Ce que fait
GetAgent **recoupe** déjà nos agents (sentiment, signaux, RSI). Seul point de veille utile : si le
**« Trade Harness »/Playbook** expose une **API** de backtest/stratégies exploitable — à surveiller,
pas à adopter aujourd'hui.

## 5. Sources

- Frais : [bitget.com/fee](https://www.bitget.com/fee) · [Spot Trading Fees & Rules](https://www.bitget.com/support/articles/12560603820584)
- BGB : [BGB Deduction of Spot Exchange Fees](https://bitget.com/en/support/articles/360060644351-Bitget-BGB-Deduction-of-Spot-Exchange-Fees)
- API : [API Intro](https://www.bitget.com/api-doc/common/intro) · [WebSocket Intro](https://www.bitget.com/api-doc/common/websocket-intro) · [Taker Buy/Sell](https://www.bitget.com/api-doc/common/apidata/Taker-Buy-Sell) · [Changelog](https://www.bitget.com/api-doc/common/changelog) · [SDK mirror](https://github.com/tiagosiebler/bitget-api)
- IA : [GetAgent launch](https://www.bitget.com/blog/articles/bitget-launches-getagent-ai-trading-assistant) · [AI Playbooks & Trade Harness](https://www.bitget.com/academy/which-crypto-exchange-has-ai-trading-playbooks-and-trade-harness-2026-guide)

## 6. Balayage support / blog / academy (18/07/2026 soir — DELTA net-nouveau)

> Faits issus des pages Bitget (support/blog/academy) + changelog UTA. **Statut = source doc :
> à VÉRIFIER contre l'API live (clé Trade-only) avant tout branchement.** Verdicts entre crochets.

### 6a. Exécution & risque (les plus actionnables)

- **Demo trading via API** — en-tête **`paptrading: 1`** + **clé API Demo** dédiée, fonds virtuels
  (~50 000 USDT), coins sim `SBTC/SETH/SUSDT/SUSDC/SEOS`, product types `sumcbl/sdmcbl/scmcbl`, WS
  `wss://wspap.bitget.com/v3/ws/public`. `/api-doc/common/demotrading/restapi`.
  **[À BRANCHER — test plomberie]** : rejouer la boucle directionnelle réelle (maker/repli taker,
  **risque n°1 double-position**, TPSL, hedge-mode) en marché live **sans argent réel**, hors murs.
- **Méthodologie de funding changée ~10/07/2026** : échantillon du premium index **1/min → 1/5 s**
  (×12) + inclut le cycle de règlement précédent ; caps/intervalles inchangés. `/support/articles/12560603887880`.
  **[À MESURER]** : recalibrer `funding_fade` et l'edge de carry (moins de « retard » minute exploitable).
- **Marge de maintenance en mode union** (notre mode) : MM = **max**( valeur_position × (MMR_tier +
  **0,06 % frais de liquidation**) ; **5 % × passif absolu** ) ; liquidation partielle jusqu'à ramener
  la MMR à ~70 % ; conversion auto des coins (haircut le plus haut d'abord). `/support/articles/12560603812664`.
  **[CORRECTION]** : ajouter le +0,06 % à la MMR de tier et le plancher 5 %-du-passif dans le calcul de
  distance de liquidation ; ne jamais supposer une liq isolée en union.
- **Position tiers (levier max par notionnel)** : BTCUSDT tier 1 = 0–150 k USDT, **MMR 0,40 %**. Le bot
  (notionnel 10–25 $, ×5) est **toujours tier 1**. **Alts illiquides** (grille 26/12/2025) : **MMR
  1,50 % dès le tier 1** (vs 0,40 % BTC) → liquidation plus proche à levier égal. `/support/articles/12560603819706`, `/12560603846455`.
  **[À MESURER]** : plancher MMR 1,5 % dans le sizing vol-targeting sur alts.
- **Delisting futures tag `ST`** : ouvertures interdites immédiatement ; à l'échéance **liq d'office au
  prix = index moyen 30 min avant**, tous ordres annulés. `symbolStatus` ∈ {`normal`,`maintain`,`limit_open`}.
  **[À BRANCHER — filtre univers]** : exclure `symbolStatus != normal` / tag ST avant d'ouvrir.
- **Specs de contrat** (`Get-All-Symbols-Contracts`) : `minTradeUSDT`=5 (mini/ordre), `sizeMultiplier`,
  `priceEndStep` (tick), `minLever`/`maxLever` 1…125. **[PRÉCISION]** confirme le filtre d'infaisabilité.
- **Types d'ordres au-delà du câblé** : Advanced limit, **Trailing stop** (callback rate), **Scaled/
  Iceberg/TWAP**, TIF **GTC/IOC/FOK**. **[À MESURER]** TWAP/iceberg = sans objet à 10-25 $ (garder pour
  une montée de taille).

### 6b. Nouvelles capacités API (changelog UTA 2026)

- **16/06/2026 — 10 nouvelles Trading Data APIs** (whale flow, ratios de marge, **volume delta taker**,
  métriques futures). **[PRIORITÉ — À MESURER]** : recoupe la « capacité non exploitée n°1 » (§2b) et
  l'audit orderflow → features à IC net de frais. **Sert directement le gate VPIN** (cf. `FORMATION_LECTURES.md` §5).
- **25/06/2026 — Get Liquidations History** (+ canal liquidations 1 s). **[À MESURER]** historique REST propre.
- **02/07/2026 — All Symbol Fee Rates API** + `positionValue`/`leverage` sur Get Account Assets.
  **[À CÂBLER]** : lire les frais maker/taker **effectifs par symbole** (VIP/BGB inclus) au lieu du dur —
  sert le plancher de spread MM et le calcul d'edge net (cohérent avec §1b).
- **RPI (Retail Price Improvement)** : **placement réservé aux market makers désignés** (pas nous), mais
  **lecture** du RPI orderbook possible (`Get RPI OrderBook`). **[VEILLE]** entrée de prix, pas un type d'ordre accessible.
- **12/05/2026 — mode delta-neutre** (`delta` + `delta-info`) ; **19/05-09/06 — isolated margin UTA +
  levier long/short séparés**. **[VEILLE]** (le bot reste en compte classique). Marché « Reality » (actions
  tokenisées) : **[VEILLE — hors univers]**.

### 6c. Produits & promotions

- **Funding-arb natif Bitget** = notre `carry` : deux réglages à voler → **porte basis-rate d'entrée**
  ((Sell−Buy)/Buy) + **batch-splitting** des jambes. **[À MESURER]** (cf. backlog `FORMATION_LECTURES.md` §6).
- **API Copy/Elite Trading** : *copier* est fee-killed (10 % profit-share, ~20-30 % des elites positifs
  net à 12 mois) ; mais le **positioning net long/short agrégé** des top traders filtrés = feed gratuit.
  **[À MESURER — vote d'ombre]** (façon `news_shadow`). Vérifier la lisibilité des positions via l'API.
- **Listing-hype** : carburant crypto récent = **EVAA/NES/ARX/RE** (juin-juil. 2026) ; **exclure les
  tickers `r*`** (actions tokenisées = bruit). Launchpool ≠ calendrier prédictif (produit réactif).
- **Limites API** : défaut 10 req/s (market data 20/s), global **6000 req/IP/min** puis **ban 5 min**,
  header `x-mbx-used-remain-limit`. **[PRÉCISION]** back-off proactif ; le ban 5 min = vrai risque si une
  boucle part en vrille (watchdog). Compte classique (pas le 250 req/s UTA).
- **Earn flexible** : intérêt journalier `montant × APR/365`, démarre le jour même si souscrit avant
  **16:00 UTC+8**, rachat instantané sans pénalité. **[PRÉCISION `liquidity_manager`]** : USDT de marge
  en flexible (jamais fixed), souscrire avant 16:00 UTC+8.
- **Levier bridé nouveaux comptes** (créés ≥ 11/02/2026 → ×5, levé 7 j après) : notre compte **antérieur =
  non affecté**. **[VEILLE]** — re-checker si on ouvre un sous-compte.

## 7. Bons usages de l'app (20/07/2026 — spot margin croisé, delta net-nouveau vs §6)

Re-lecture ciblée (WebFetch support/academy Bitget, pas de scraping). §6 couvre déjà exec/risque
**futures/union** ; ci-dessous le DELTA **spot margin** (surface `margin_trader`/`alt_carry` en croisé) :
- **Levier spot margin : croisée ×3 max · isolée ×10 max.** La croisée d'alt_carry est donc plafonnée
  ×3 côté Bitget (sous le mur ×5 du bot). `/support/articles/12560603820651`.
- **Auto-borrow ON par défaut** (emprunte le nécessaire à l'ordre, contrôlé par le levier) · **auto-repay**
  = Quick Repay / close-at-market. = exactement ce que fait alt_carry (`sideEffectType`). Bon usage confirmé.
- **Liquidation spot margin** : **margin level ≥ 1,0** → liquidation ; **0,8** → margin call ; **frais 2 %**
  du montant liquidé. → surveiller le margin level croisé, ne jamais approcher 0,8.
- **Post-only** = ordre limite qui garantit le rôle **MAKER**, **auto-annulé s'il croiserait** = exactement
  le `FUTURES_EXEC_STYLE=maker` du bot (le levier-frais prouvé). **TP/SL = reduce-only** ; OCO/trailing/trigger
  dispo (déjà en §6a).
- ⚠️ **« BGB Futures Burn −15 % / lock 2000 BGB / Fee Vault »** = claim de sources TIERCES (metapress/bitqed)
  **NON confirmé** par la page fees autoritative (qui ne cite que « holdings BGB → VIP »). **NON acté**
  (ERR-003) ; non-viable de toute façon (lock ~1–3k$ pour un volume futures minuscule). [VEILLE]
- **VIP1** = 500k vol 30j **OU** 30k solde **OU** 20k BGB → **hors de portée** du bot.

**Bilan formation** : le bot utilise DÉJÀ les bons mécanismes (post-only/maker, auto-borrow/repay, BGB
spot+marge à 0,08 %). Aucun changement requis ; seul risque de propre-usage à surveiller = le **margin
level** de la croisée (liquidation ≥ 1,0). Consommation du BGB marge = preuve que la remise s'applique.

## 8. Mining bitget.com (20/07/2026 — ADL/assurance, frais maker négatifs, Earn approfondi)

### 8a. Fonds d'assurance & ADL (auto-deleveraging) — RISQUE futures [net-nouveau]
- **Fonds d'assurance** : couvre le shortfall quand prix de liquidation < prix de faillite ; absorbe la
  marge restante sinon. `/support/articles/360059239211`.
- **ADL déclenché quand le fonds d'assurance du coin est ÉPUISÉ** → force-close des contreparties SANS
  passer par le marché, au **mark price**, sans frais. `/support/articles/12560603800805`.
- **ADL score** (qui est deleveragé en 1er) : croisée/multi-actifs profitable = `ROI × MMR_compte` ;
  perdant = `ROI ÷ MMR`. **Les positions PROFITABLES à fort levier sont deleveragées EN PREMIER.**
- **Réduire le risque ADL (par ordre d'efficacité)** : **baisser le levier** (le + efficace), fermer les
  positions profitables, **hedging / DELTA-NEUTRE** (rangé plus bas dans la file ADL), diversifier.
- **✅ PERTINENCE BOT (positive)** : le **carry est DELTA-NEUTRE** (long spot / short futures) + levier
  ≤×5 + taille minuscule → **risque ADL structurellement bas** (rangé bas dans la file). Le design du bot
  minimise déjà l'ADL. Rien à coder ; à savoir : ne jamais monter le levier sur une jambe NUE (non couverte).

### 8b. Frais maker NÉGATIFS / Market Maker Program — le levier-frais [confirmation + veille]
- Les **market makers désignés** touchent des **frais maker NÉGATIFS (rebates = payés pour coter)** :
  spot Group A (BTC/ETH/SOL/XRP/DOGE/BGB) **MM1 −0,010 %** … MM5 0,000 %. Futures : maker 0,008→0 % par
  tier PRO. `/support/articles/12560603880982`, `/12560603850208`.
- **Éligibilité = application + règles d'assessment (programme MM), PAS accessible au retail/petit compte.**
  → **le bot (25 $/trade) NE qualifie PAS.** Confirme que **maker = LA direction** (jusqu'à −0,01 % pour
  les MM) ; le bot capte au mieux le taux maker standard via post-only. **[VEILLE]** : si un jour le bot
  atteint une profondeur/volume MM, ces rebates seraient transformateurs (get-paid-to-quote).
- **VIP** : sources divergent (VIP1 = 30k solde OU 1M volume selon `/880982` ; vs 500k/30k/20k BGB §7).
  Peu importe : **hors de portée**. Volume des bots Spot-Margin/Futures-Grid compte pour le VIP (inutile ici).

### 8c. Earn approfondi (liquidity_manager) [candidats mesure]
- Au-delà du flexible (déjà utilisé, §6) : **Auto-Earn sur marge IDLE** (rendement auto sur la marge
  oisive) = **candidat direct pour `liquidity_manager`** (yield sur l'USDT de marge dormant). **[À MESURER]**.
- **Structured** (Dual Investment, Shark Fin, Smart Trend) = principal-garanti mais **PAS flexible**
  (lock/conditionnel) → **inadapté** au besoin de liquidité redéployable du bot. **[VEILLE]**.
- Rendements : stablecoins ~10 % APY, BTC/ETH 5-8 %, **XAUT flexible jusqu'à 15 % APR** (promo VIP — le
  bot détient du XAUT ; à vérifier l'accès). `/earning`.
