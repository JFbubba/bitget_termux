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

**Prochaine action de dev (quand l'utilisateur dit « go »)** : construire
l'**assistant conversationnel** (bot Telegram « assistant » → Claude Haiku par
défaut, agnostique via `LLM_BASE_URL`/`LLM_MODEL`) avec accès en outils aux
readers read-only existants. Nécessite `ANTHROPIC_API_KEY` dans `.env`.

**Option en attente proposée** : ajouter `LLM_BASE_URL` / `LLM_MODEL` à
`.env.example` pour garder l'option Kimi/Ollama ouverte.

**Historique des commits de la session** (branche `claude/beautiful-heisenberg-c5aoqu`) :
dashboard web → readers keyless (Fear&Greed/DeFi/token-safety/DEX) → câblage
Telegram + panneau marché → outillage env (.env.example/check_env/ENV_SETUP) →
docs de continuité (PROJECT_STATE/DATA_SOURCES). Tests 49/49, SAFE, push OK.

