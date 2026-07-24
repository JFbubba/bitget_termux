# Outils & sources externes — revue curée (lecture seule)

Revue de ~32 sources fournies (données, bots, serveurs MCP, skills Claude,
Polymarket) pour améliorer le projet **sans introduire de trading réel
automatique**. Tout ce qui est retenu reste **lecture seule / aide à la
décision**. Les outils de ce document restent en lecture seule ; l'exécution réelle du
bot est cantonnée aux modules audités (`spot_executor` réel §44, `futures_executor` borné
§45, surfaces §67) — voir CLAUDE.md « État réel vs paper ». (Cadrage historique « moteur
paper `can_trade=False` » périmé depuis §44/§45.)

Tri : **ADOPTER** (gratuit/légitime, exploitable) · **CONSIDÉRER** (utile mais
payant / lourd / à réimplémenter) · **ÉVITER** (scam, malware, exécution à risque).

---

## ⛔ À ÉVITER — scams / malware confirmés

| Source | Pourquoi |
|---|---|
| `Maestro-Trading-Bot/Maestro-Bot` | Pas de code source, README → installeurs `.exe`/`.dmg` externes, demande les clés exchange. Probable credential-stealer. |
| `Maestro-Sniper-Bot` (org) | Coquille marketing, aucun code, boutons "download". Même schéma. |
| `Cortex-AI-Network/crypto-arbitrage-bot-automated-trading` | `.exe` depuis `arbitrage-bot.pro`, « rendement horaire garanti », demande de connecter les clés. Scam. |
| `BlackSky-Jose/PolyMarket-trading-AI-model` (skillsllm) | Exécution live, auteur inconnu, flag de scan. |

**Règle générale :** tout repo « bot » sans code source, avec téléchargement
`.exe`/`.dmg`, ou qui réclame une **clé privée / seed phrase** → NON.

> Cas particulier `1fge/pump-fun-sniper-bot` : le code est **réel et non
> malveillant** (signature locale, pas d'exfiltration), mais archivé, sans
> licence, et la stratégie (sniper de mints pump.fun) est perdante. À lire pour
> les idées d'infra uniquement, **jamais exécuter**.

---

## ✅ Données & signaux (gratuits, légitimes, lecture seule)

| Source | Donnée | Verdict |
|---|---|---|
| **CFTC COT** (vu via Tradingster) | positionnement hebdo des gros acteurs sur futures crypto | **ADOPTER** (tirer depuis la source CFTC, pas scraper) |
| **Clusters de liquidation + CVD / order-flow** | zones de liquidation, déséquilibre acheteur/vendeur | **ADOPTER** (auto-calculé depuis OI / funding / order book Bitget/CoinDesk) |
| **Trading Economics** | calendrier macro + indicateurs (CPI, taux, DXY…) | **CONSIDÉRER** (calendrier gratuit ; API payante) |
| **Unbiased Level Pro** (TradingView, payant/closed) | *concept* : niveau S/R ancré au plus gros volume + score de biais volume + confluence multi-TF | **CONSIDÉRER → réimplémenter le concept** (fait, voir `indicators.py`) |
| investingLive, imprimantetrading | news / édu, pas d'API | ÉVITER / faible valeur |

---

## ✅ Serveurs MCP (à ajouter côté PC, lecture seule)

- **`prediction-mcp` (Polymarket + Kalshi)** — **ADOPTER**. Le **seul vraiment
  crypto-pertinent** : odds/sentiment sur BTC, ETH, décisions Fed, ETF.
  **Gratuit côté Polymarket** (lecture publique, sans clé). Ajout (Windows) :
  ```
  claude mcp add -s user prediction -- cmd /c npx -y prediction-mcp
  ```
  (épingler une version : projet en début de dev).
- **`sec-edgar-mcp`, `OpenInsider-MCP`, `Equibles`** — bien faits mais
  **actions US** (filings SEC, insiders, FRED/CFTC). **CONSIDÉRER** seulement si
  tu suis aussi des actions US (Coinbase, MicroStrategy, mineurs).
- **`unusual-whales-mcp` (payant ~50 $/mois)**, **CongressMCP** (législatif) —
  **ÉVITER** pour notre cas (coût / hors-sujet crypto).

---

## ✅ Patterns de skills Claude (à adapter dans notre repo)

- **`tradermonty/claude-trading-skills`** (57 skills, MIT) — **ADOPTER** :
  meilleur squelette `SKILL.md` (frontmatter → déclencheur → dépendances API →
  *decision gates* → artefacts in/out → références) et le **bloc disclaimer**
  (« pas un conseil financier, pas un service de signaux, pas un broker ; les
  backtests ne garantissent rien ; l'utilisateur assume ses décisions »).
  Discipline **analyse, pas exécution**.
- **crypto-market-research-agent** (microck) — **ADOPTER le pattern** : essaim
  d'agents parallèles (prix / sentiment / macro / news), **tiers** léger (Haiku)
  vs complet (multi-modèle), sorties **horodatées** (piste d'audit).
- **Anthropic Finance Agents** (officiel) — **ADOPTER la gouvernance** :
  **permissions par outil + journal d'audit** ; connecteur **FMP** (couvre le crypto).
- **Claude for Financial Services** (officiel) — **ADOPTER** l'**attribution de
  source** (chaque chiffre traçable, vérifier avant d'agir) + analyse
  **EV / root-cause**.
- **`Polymarket/agent-skills`** (officiel) + **`harish-garg/Claude-Plugin-Marketplace-for-Polymarket`**
  — **ADOPTER** le **sous-ensemble lecture seule** : `SKILL.md` à divulgation
  progressive, structure de *plugin marketplace* (`/plugin marketplace add .`),
  connecteurs Gamma/Data/WebSocket. Laisser le trading CLOB de côté.
- **`Polymarket/agents`** (officiel, MIT) — **CONSIDÉRER** la couche
  connecteur / RAG-news / modèles Pydantic ; **ÉVITER** le code à clé privée.

---

## 🧠 Concepts d'architecture à reprendre

- **Orallexa** (paper-only, MIT) : **fusion de signaux** hétérogènes dans un
  espace de probabilité commun → **débat Bull / Bear / Judge** (réduit le biais
  d'un seul modèle) → **gate de risque** (veto final) avant toute conclusion.
- **MiroFish** (AGPL — copyleft, ne pas *vendoriser*) : **graphe de relations
  GraphRAG** construit depuis news/rapports + **scénarios de stress nommés**
  (choc de taux, depeg, action régulatoire) → produire une **distribution** de
  résultats, pas un point.
- **pump-fun bot** (idées d'infra, repurposées en lecture seule) : ingestion
  **multi-endpoint** + abonnement **WebSocket** + **journal d'événements** ;
  plafond de risque par item (vu chez `ai-trade-agent`).

---

## 🚀 Plan d'adoption priorisé (SAFE, aucun ordre réel)

1. **[fait]** Indicateurs volume : `volume_anchored_level` + `volume_bias_score`
   (concept Unbiased Level Pro réimplémenté) → `indicators.py` + tests.
2. **`prediction-mcp` côté PC** (Polymarket, gratuit) → odds/sentiment crypto.
3. **Module CVD / order-flow + zones de liquidation** depuis données
   Bitget/CoinDesk (OI, funding, order book).
4. **Squelette de skill « analyse »** (disclaimer + permissions par outil)
   inspiré de `tradermonty` + gouvernance Anthropic.
5. **CFTC COT** hebdo comme couche de contexte/positionnement.

Aucune de ces adoptions n'ajoute `place_order` / `open_*` / `close_position` /
`cancel_order` / `change_leverage` / `transfer` / `withdraw`.
