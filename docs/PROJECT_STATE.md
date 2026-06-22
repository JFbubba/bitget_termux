# PROJECT STATE — bitget_termux

> Document de continuité. Si la conversation est compressée/résumée, **ce
> fichier (+ `docs/DATA_SOURCES.md`) contient tout le nécessaire pour reprendre
> le développement sans perte.** Langue de travail : français.

_Dernière mise à jour : 2026-06-22._

## 1. Vision
Système d'**intelligence de trading crypto** pour l'utilisateur (jeanfminet) :
- **Assistant conversationnel** (langage naturel) + **dashboard web** (style terminal sombre).
- Suivi de signaux (X / Farcaster / Telegram), **détection de scams/rugs**,
  données GMGN/Jupiter/DEX/CEX, marchés de prédiction (Polymarket).
- Hébergé sur un **VPS**. But : aide à la décision pour faire du profit. Tout en
  **paper / analyse**, jamais d'exécution réelle.

## 2. ⚠️ PÉRIMÈTRE SÛR — À LIRE EN PREMIER (limite non négociable)
Le projet est **lecture seule / analyse / détection / paper**. Règles dures :
- **`can_trade=False` partout. AUCUN ordre réel n'est exécuté.** Le moteur
  *propose* des ordres ; il ne les envoie jamais.
- **On NE construit PAS** : création automatique de tokens sur pump.fun,
  promotion coordonnée via comptes X/sociaux, bots de **sniping**, ni rien qui
  relève du **pump-and-dump / manipulation de marché / scam-token**. Ça nuit aux
  acheteurs et est probablement frauduleux. Les liens de la liste vers des bots
  sniper/pump.fun (Maestro, pump-fun-sniper…) ne sont **pas** répliqués.
- **On construit** : **DÉTECTION** scam/rug/honeypot (pour éviter), écoute de
  signaux **read-only** (sentiment), données marché, paper trading, backtest,
  dashboard, assistant conversationnel.
- « rugpull inversé » / « sniper » = interprétés dans leur **forme saine** :
  détecter des lancements pour s'en protéger/les analyser, jamais pour pumper.
- **Jamais de secret dans le chat.** Les clés vivent uniquement dans `.env`
  (gitignoré) ou les credentials n8n.

## 3. Machinerie de sécurité (doit rester verte)
- **`security_agent.py`** — scanne `FILES_TO_SCAN` pour mots-clés dangereux
  (place_order, transfer, withdraw, set_leverage…). Doit afficher `VERDICT: SAFE`.
- **`safe_push_check.sh`** — à lancer **AVANT chaque push** : bloque fichiers
  interdits (.env, clés, .csv…), scanne secrets, grep `*.py` pour mots dangereux
  (exclut security_agent/getagent_audit/tests_audit), lance `tests_audit.py`.
  Doit finir `SAFE PUSH CHECK OK`, **exit 0**.
- **`tests_audit.py`** — actuellement **49/49**.
- **Piège connu** : le mot **`transfer`** est un mot-clé dangereux scanné. À
  éviter comme sous-chaîne littérale dans les `.py` scannés (ex. `token_safety.py`
  saute le champ GoPlus `transfer_pausable`).
- **Piège Bash** : capturer le **vrai** code retour (`cmd; RC=$?`), pas
  `PIPESTATUS` d'un `grep` — un commit était passé avec un test rouge à cause de ça.

## 4. Workflow de dev
- **Branche** : `claude/beautiful-heisenberg-c5aoqu`. Développer + pousser là **uniquement**.
- Cycle : éditer → `python tests_audit.py` → `python security_agent.py` →
  `bash safe_push_check.sh` (vrai exit) → commit → `git push -u origin <branche>`
  (retry backoff 2/4/8/16s).
- Trailers de commit : `Co-Authored-By: Claude…` + `Claude-Session:…`.
- Ne jamais pousser sur une autre branche. Pas de PR sauf demande explicite.
- Ne jamais committer l'ID de modèle dans le repo.

## 5. Composants (construits)
- **Moteur** (existant) : signaux, confluence, order-flow, macro, paper, stats,
  bot Telegram. `can_trade=False`.
- **Sécurité** : `security_agent.py`, `safe_push_check.sh`, `tests_audit.py`.
- **`dashboard/`** : serveur HTTP stdlib (`server.py`) + `index.html` (sombre
  monospace : perf, probability lattice, order-flow, macro, panneau MARKET,
  graphe relationnel type MiroFish). `/api/state` JSON. `DEPLOY.md` (VPS : clé
  SSH, ufw, tunnel, systemd). Bind par défaut **127.0.0.1** (sécurisé).
- **Readers keyless** (validés en réel) : `sentiment_index.py` (Fear&Greed),
  `defi_data.py` (DefiLlama), `token_safety.py` (GoPlus+Honeypot.is+RugCheck =
  **détection** rug/honeypot, niveaux CRITICAL/HIGH/MEDIUM/LOW), `dex_scanner.py`
  (DexScreener).
- **Commandes Telegram** ajoutées : `/feargreed /defi /rugcheck /dexsearch
  /envcheck` (+ existantes `/stats /orderflow /macro /confluence /signals /preorders`).
- **Env tooling** : `.env.example` (toutes les clés, vides à remplir),
  `check_env.py` (vérif **masquée** — jamais la valeur), `ENV_SETUP.md`, `/envcheck`.

## 6. Hébergement
- VPS **Hostinger KVM2** (2 vCPU / 8 Go / 100 Go), Ubuntu 24.04, **n8n** présent,
  **IP fixe** (→ whitelist Bitget possible). User SSH = `root`. Déploiement via
  `dashboard/DEPLOY.md` (clé SSH, ufw, tunnel SSH `ssh -L 8787:localhost:8787`, systemd).
- Token API **Hostinger** → credentials **n8n**, PAS dans le `.env` de trading.

## 7. Décision LLM / assistant
- **Assistant conversationnel = prochaine grosse pièce.** Modèle par défaut :
  **Claude Haiku 4.5** (`claude-haiku-4-5`) — pas cher ($1/$5 par 1M), excellent
  en tool-use. ~centimes/question, ~1–3 $/mois en perso → ne mange pas la marge.
- **Agnostique au modèle** : `ANTHROPIC_API_KEY` par défaut + `LLM_BASE_URL` /
  `LLM_MODEL` optionnels pour brancher Kimi/Moonshot, DeepSeek ou Ollama local.
- LLM local sur VPS 8 Go sans GPU = trop faible pour un agent à outils ; upgrades
  payants Ollama/LMStudio **non recommandés** (marge).
- MCP dispo en session de build pour la data : **CoinDesk** (riche), Bigdata.com,
  prediction-mcp (Polymarket).

## 8. Roadmap / TODO
1. **Assistant conversationnel** (bot Telegram « assistant » → Claude avec outils :
   order-flow, macro, confluence, rugcheck, defi, dexsearch, stats, web search).
   Nécessite `ANTHROPIC_API_KEY`. Construire agnostique (Haiku par défaut).
2. **Readers à clé** quand l'utilisateur fournit les clés : CoinGecko, CryptoPanic,
   FMP (macro+calendrier), Birdeye/Helius (Solana), Neynar (Farcaster), X (sentiment).
3. **Dashboard** : panneau « nouveaux tokens / trending » (DexScreener), panneau détection.
4. Alt-data via MCP (basse prio, actions US) : OpenInsider, SEC EDGAR, Congrès, Unusual Whales.
5. Détection d'**arbitrage** (read-only).
6. Brancher les données **CoinDesk MCP** dans l'analyse.

## 9. Données — voir `docs/DATA_SOURCES.md`
Liste complète des sources (keyless construites, à-clé en attente, MCP dispo) et
le verdict de couverture des 32 liens de `outils_trading.md`.

## 10. État courant / point de reprise (2026-06-22)
**En cours** : mise en place du VPS et du `.env` par l'utilisateur.
- SSH : l'avertissement « REMOTE HOST IDENTIFICATION HAS CHANGED » a été résolu
  (`ssh-keygen -R 187.77.67.45` puis acceptation de la nouvelle empreinte
  ED25519 `SHA256:g1ilpIgrH9P9wkRkWAEAOlwK8Vq4pbieENlRkuMs5Bo`).
- Blocage actuel : `Permission denied (publickey,password)` malgré reset du mot
  de passe root. Causes probables : `PermitRootLogin prohibit-password` (login
  root par mot de passe désactivé en SSH), reset pas encore appliqué (reboot),
  ou clavier/typo. **Contournement conseillé** : utiliser le **terminal
  navigateur Hostinger** (hPanel → VPS → Console) qui contourne SSH, pour faire
  le `.env` directement ; puis mettre en place des **clés SSH** (ssh-keygen sur
  le PC → coller la clé publique dans `~/.ssh/authorized_keys` du VPS).
- Étapes `.env` : `cp .env.example .env` → `nano .env` (coller clés) →
  `python check_env.py` (ou `/envcheck`). Clés X = optionnelles.

**Assistant conversationnel : SQUELETTE CONSTRUIT** (`assistant/`).
- `assistant/llm_client.py` : Anthropic Messages (Haiku) **ET** OpenAI-compatible
  **avec outils** (Groq/Gemini/Ollama/Kimi). Bascule auto sur OpenAI dès que
  `LLM_BASE_URL` est défini. Charge le `.env` racine. (Note billing : l'API
  Anthropic exige des crédits prépayés → l'utilisateur a choisi la voie GRATUITE
  via Groq/Gemini, d'où le chemin OpenAI complet.)
- `assistant/tools.py` : 8 outils LECTURE SEULE (order-flow, macro, confluence,
  check_token_safety, defi, search_dex, fear_greed, trade_stats). Aucun ordre.
- `assistant/agent.py` : boucle agentique (tool_use) + CLI
  `python assistant/agent.py "question"`. Nécessite `ANTHROPIC_API_KEY`.
- Telegram : commande `/ask QUESTION` (subprocess vers agent.py).
- `.env.example` : `LLM_MODEL/LLM_PROVIDER/LLM_BASE_URL/LLM_API_KEY` ajoutés.
- Testé : outils en réel, boucle via LLM factice (51/51), security SAFE.

**Indicateurs techniques** : `technicals.py` (réutilise `indicators.py`) — VWAP,
Volume SMA, Volume Profile (POC/VAH/VAL ~ VPVR/VPSV), TPO (temps-prix), RSI14,
ATR14, EMA20/50, biais volume, clusters de liquidité du carnet (~ OB heatmap).
Exposés à l'assistant : outils `get_technicals` + `get_liquidity_clusters`.
À FAIRE (multi-exchange) : funding agrégé OI-pondéré 8h, OI agrégé en bougies
(Binance+Bybit+Bitget ou MCP CoinDesk). Vision charts : option Gemini/Claude.

**Prochaine action** : l'assistant est **LIVE et fonctionnel sur le VPS** via
**Groq gratuit** (`LLM_BASE_URL=https://api.groq.com/openai/v1`,
`LLM_MODEL=llama-3.3-70b-versatile`). Testé : appelle les outils + synthétise en
quelques secondes. (Ollama `qwen2.5:7b` local marche aussi mais trop lent en CPU
8 Go → réservé au 100 % local patient, via `LLM_TIMEOUT` élevé.)
Itérer ensuite : bridge Telegram (`/ask` depuis le tél, besoin du token Telegram),
mémoire de conversation, outils news/prix (clés CryptoPanic+CoinGecko déjà là),
multi-exchange (funding/OI agrégés), vision charts (Gemini/Claude).

**FAIT — bridge Telegram LIVE** : 2 bots (TELEGRAM_BOT_TOKEN=alertes,
COMMAND_BOT_TOKEN=assistant). Bot assistant tourne en service systemd
(`deploy/bitget-bot.service`, `systemctl ... bitget-bot`) → `/ask /price /news`
+ toutes les commandes répondent depuis le téléphone. Outils news (CryptoPanic)
+ prix/marché (CoinGecko) ajoutés. **13 outils** au total dans l'assistant.
Reste : mémoire de conversation, multi-exchange (funding/OI agrégés), vision charts,
déploiement du dashboard web, clés Bitget (optionnel, pour solde/compte).

**FAIT aussi** : #3 **mémoire de conversation** (`assistant/memory.py`,
`conversation_state.json` gitignoré, `/forget`) ; #4 **funding/OI agrégés
multi-exchange** (`aggregated_derivs.py` — Binance+Bybit+Bitget, les 3 répondent
depuis le VPS Frankfurt, funding 8h OI-pondéré + OI total ; outil
`get_aggregated_derivs` + `/deriv`). **15 outils** dans l'assistant.
Reste : #5 vision charts, #6 déploiement dashboard web, #7 clés Bitget,
+ "OI historique en bougies" (dernier indicateur de la liste, optionnel).

**FAIT — #5 charts & vision** : `chart.py` (matplotlib) rend bougies+VWAP/EMA/POC/
volume depuis les données Bitget → `/chart SYMBOL [TF]` envoie l'image (généré dans
/tmp, pas d'accumulation). `assistant/vision.py` analyse une image envoyée
(Gemini, `VISION_API_KEY`). Granularité normalisée (1h→1H). Le bot assistant
répond par SON token (`reply_text`/`reply_photo`). Reste : #6 dashboard web,
#7 clés Bitget, + OI historique (optionnel).

**FAIT — #6 dashboard + Polymarket** : dashboard web DÉPLOYÉ (service systemd
`bitget-dashboard`, actif, 127.0.0.1:8787, vu via tunnel SSH
`ssh -L 8787:localhost:8787`). `polymarket_data.py` (Gamma public-search,
keyless, lecture seule) → outil `get_prediction_markets` + `/poly` : cotes des
marchés de prédiction (sentiment, PAS de pari). **16 outils** dans l'assistant.
Reste UNIQUEMENT : #7 clés Bitget (optionnel, solde/compte), OI historique (option).

**FAIT — risk engine** : `risk_manager.py` — `check_trade()` (caps
position/levier/positions ouvertes/perte journalière via env `RISK_*`) +
`kill_switch_active()` (fichier `KILL_SWITCH` ou `TRADING_HALT=1`). Fondation de
la future couche d'exécution. LECTURE SEULE, aucun ordre.

**FAIT — cerveau « essaim »** : `swarm_brain.py` — 5 agents spécialisés
(`orderflow`, `technicals`, `macro`, `sentiment`, `derivs`), chacun vote
[-1..1] + confiance. `aggregate()` (pur) = consensus pondéré → biais
LONG/SHORT/NEUTRE + conviction. **S'éduque en ligne** : `_record` journalise,
`learn()` juge les décisions après `BRAIN_HORIZON_S` (3600s) contre le prix réel
et `update_weights()` renforce/affaiblit les agents (bornes [0.2,3], normalisé).
Persistance `brain_weights.json` + `brain_log.json` (gitignorés). `peek()` =
lecture sans écrire (pour le polling dashboard). Outil assistant
`get_brain_read` + commande `/brain SYMBOL`. **17 outils**. Tests purs ajoutés
(consensus/seuils, pondération, normalisation, renforcement, bornes).

**FAIT — dashboard interactif** : `dashboard/index.html` rendu « plus
dynamique » et chaque couche est isolable. Barre d'indicateurs du graphique
(Bougies/EMA20/EMA50/VWAP/Volume, calculés côté client) — clic=toggle,
double-clic=isoler ; crosshair + tooltip OHLC au survol ; légende du graphe
relationnel cliquable (toggle/isoler bear/bull/catalyst/cluster) ; nouveau
panneau « Cerveau · Essaim » (biais + 5 agents, chaque agent isolable au clic),
alimenté par `swarm_brain.peek` via `build_state` (clé `brain`, cache 45s).

**Option en attente proposée** : ajouter `LLM_BASE_URL` / `LLM_MODEL` à
`.env.example` pour garder l'option Kimi/Ollama ouverte.

**FAIT — sources hautes valeur (liste outils_trading.md)** :
- `liquidations.py` : carte de liquidations (clusters/heatmap) prix×levier×OI réel
  → **6ᵉ agent du cerveau** + panneau dashboard + `/liq`.
- `econ_calendar.py` : calendrier éco keyless (Forex Factory) → `/calendar`.
- `arbitrage.py` : détection d'écarts (spot/base/funding), read-only → `/arb`.
- `macro_data.py` (yfinance, **dép. optionnelle**) : TradFi temps quasi-réel
  (VIX/DXY/SPX/10Y/or/WTI/BTC) → enrichit l'agent macro + `/tradfi`.
- `ccxt_markets.py` (ccxt, **dép. optionnelle**) : prix/funding multi-exchange
  read-only → `/cross`.
- `backtest_brain.py` : backtest hors-ligne du signal **technique** du cerveau
  (hit-rate, rendement vs buy&hold, Sharpe, DD) → `/backtest`.
- Dashboard : graphique **TradingView Lightweight Charts** (vendorisé,
  `dashboard/vendor/`, route statique sûre) remplaçant le canvas maison.
- **23 outils** assistant. Dépendances optionnelles : `requirements-optional.txt`
  (`pip install -r` sur le VPS pour yfinance/ccxt). Tests 84/84, SAFE.

**Prochaine étape majeure (en attente de l'utilisateur)** : couche d'exécution
autonome. Pré-requis explicites : clés Bitget **read+trade (JAMAIS withdraw)**,
IP whitelistée, `dry-run` par défaut derrière `risk_manager`, réorientation du
`security_agent` (aujourd'hui il bloque tout mot-clé d'ordre). Le cerveau
fournit déjà le signal ; il manque l'exécuteur gardé + la boucle autonome.

**Historique des commits de la session** (branche `claude/beautiful-heisenberg-c5aoqu`) :
dashboard web → readers keyless (Fear&Greed/DeFi/token-safety/DEX) → câblage
Telegram + panneau marché → outillage env (.env.example/check_env/ENV_SETUP) →
docs de continuité (PROJECT_STATE/DATA_SOURCES). Tests 49/49, SAFE, push OK.

