# BITGET_REFERENCE.md — référentiel Bitget (frais, API, WebSocket, écosystème IA)

Référentiel **durable** des faits Bitget qui conditionnent les décisions du bot. But : arrêter
de raisonner sur des hypothèses/mémoire et s'appuyer sur les sources **autoritatives**.

> ⚠️ **Discipline de source.** `bitget.com` **bloque le WebFetch (403, anti-bot)** — il n'y a
> donc PAS de scrape frontal du site (ce qui invalide « scraper l'entièreté du site »). Ce doc
> est grondé via : le **SDK officiel mirroré** (`github.com/tiagosiebler/bitget-api`, fetchable),
> le **centre de support Bitget**, et la recherche des pages officielles. Tout ce qu'on
> voudrait **brancher** doit d'abord être **vérifié contre l'API réelle** (clé Trade-only,
> lecture) — un endpoint documenté n'est actionnable qu'une fois testé avec notre clé.
>
> Dernière mise à jour : **18/07/2026**.

---

## 1. Frais & déduction BGB (autoritative)

| Marché | Maker | Taker | Déduction BGB (−20 %) |
|---|---|---|---|
| **Spot** | 0,10 % | 0,10 % | ✅ **→ 0,08 %** (frais payés en BGB) |
| **USDT-M perp** | 0,02 % | 0,06 % | ❌ **ne s'applique PAS aux futures** |
| **COIN-M** | ~0,02 % | ~0,06 % | ❌ (à confirmer contre l'API) |

- **BGB = SPOT UNIQUEMENT, −20 %**, activable dans les réglages du compte (« payer les frais en
  BGB »). Confirmé par le support Bitget. → tranche l'ancienne incertitude « BGB futures » :
  **non applicable au futures**.
- **VIP** : chaque +50k USDT de volume 30j baisse les deux côtés (spot ET futures) ; atteignable
  aussi par solde d'actifs ou holdings BGB.
- **Empilement** BGB + VIP + parrainage → jusqu'à ~−65 % (spot ~0,04–0,05 % all-in).

**Implication bot (net de frais).** Côté **spot**, la barre = ~0,08 %/côté (0,16 % aller-retour)
au lieu de 0,10 %. Côté **futures**, **pas de remise BGB** : 0,06 % taker / 0,02 % maker restent
le taux réel. → Le levier **maker** (futures 0,06 → 0,02, −67 %) est bien plus fort que BGB pour
le **directionnel** ; BGB n'allège que le **spot** (accumulation, listing-hype, market making).
Cohérence à faire : `listing_hype` (spot) devrait modéliser 0,08 %, pas 6 bps pleins.

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

> Les pages `bitget.com` étant 403 au WebFetch, une mise à jour plus profonde (SPA) passerait par
> le **scraper du data_collector** (scrapling, venv isolé) ou une vérification directe **contre
> l'API** avec notre clé. Ne jamais confier l'exécution à un outil externe (murs constitutionnels).
