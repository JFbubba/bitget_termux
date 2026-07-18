# CLAUDE.md — contexte & règles pour tout agent travaillant sur ce dépôt

Bot de trading Bitget avec un **cerveau en mixture-of-experts** (14 agents déterministes,
pondération adaptative EARCP assainie §51 : hit-rates EWMA exogènes, cohérence
leave-one-out, lissage — banc déterministe GELÉ à 14, §62). **LLM/réseaux de neurones
AUTORISÉS depuis le 06/07/2026** (décision propriétaire — l'ancienne contrainte « aucun
réseau de neurones » du §1 est LEVÉE). Ils sont branchés en **surcouches opt-in** (agent
LLM 15ᵉ, `llm_agent.py`, gated `LLM_AGENT_ENABLED`, défaut OFF ; **réseau neuronal de
fusion 16ᵉ voix, `nn_agent.py`/`neural_net.py` — MLP PyTorch entraîné sur les votes du
banc, gated `NN_AGENT_ENABLED`, défaut OFF, §65 ; stratégies classiques 17ᵉ voix,
`classics_agent.py` — MACD/Bollinger/Donchian/VWAP/grille/pairs du laboratoire, gated
`CLASSICS_AGENT_ENABLED`, défaut OFF, §72 ; **circuit quantique 18ᵉ voix,
`qml_agent.py`/`qml_quantum_sim.py` — variationnel 6 qubits entraîné au labo
(`qml_prototype/`), inférence numpy PURE (ERR-004), gated `QML_AGENT_ENABLED`, défaut
OFF, porte d'edge, §100**) : **déterministe d'abord**
(le banc 14 reste le socle), **fail-safe** (LLM/NN indispo/lent/incohérent → vote ignoré,
jamais de crash ni de blocage), et surtout **les murs argent de `guards()` restent ABSOLUS
et déterministes** — un LLM peut influencer la direction/le sizing suggéré, jamais desserrer
les caps 50/250, le levier ×5, le stop journalier, le kill-switch ou la porte d'edge.
Tourne sur un VPS Ubuntu (`~/bitget_termux_repo`).
Branche de travail : `claude/beautiful-heisenberg-c5aoqu`.
Cadences (§63) : cerveau 1 min (timer dédié bitget-brain), scan ~1 min,
watchdog 5 min (carte de fraîcheur « rien d'aveugle » §61), notify 15 min,
validation 6 h (porte PROFONDE 6 ans §54), sauvegarde chiffrée Telegram 03:40,
revue hebdo dimanche 18:00 (recommandations chiffrées automatiques §60).
Boucles via CRONTAB (pas systemd — ne PAS doubler avec deploy/install_learning_timers.sh) :
accumulation 12:00, neural-train 04:20, learning-health toutes les 6 h,
strategy-lab dimanche 05:00 (§68/§70).

## ⚠️ RÈGLES D'ENGAGEMENT (révisées le 02/07/2026 — décision propriétaire, §45)

1. **Argent réel en jeu.** Seuls des modules d'exécution AUTORISÉS et audités passent des
   ordres réels ; chacun est classé à part par `security_agent` + `safe_push_check` :
   - `spot_executor.py` : achat spot BTC d'accumulation, ≤5 $/j, jamais de vente/retrait ;
   - `futures_executor.py` : futures BORNÉ (§45) — marge ISOLÉE, levier ≤×5, murs en dur
     50 $/trade et 250 $ cumulé (env/config peuvent abaisser, JAMAIS dépasser), stop de
     perte journalier (−5 % -> kill-switch), jamais de retrait/virement/annulation ;
   - surfaces bornées §67 (`spot_trader`, `margin_trader`, `account_transfers`,
     `earn_manager`) sur le noyau `bitget_execute` : **toutes défaut OFF**, DRY par défaut,
     caps durs, kill-switch fail-closed. RETRAIT interdit partout (clé Trade-only).
   Le cerveau/scan/pré-ordres restent paper tant qu'ils ne passent pas par ces modules.
2. **Délégation totale (§92, 07/07/2026)** : « Je soussigné propriétaire, t'accorde le
   droit de prendre des initiatives de façon autonome, je t'accorde le droit de
   commande sur tout le compte Bitget […] je souhaite déléguer totalement la gestion
   de ce bot à lui-même. » Les LEVIERS D'EXPLOITATION (verrous LIVE, caps effectifs,
   voix opt-in, notional, floats, promotions mesurées) se gèrent donc EN AUTONOMIE —
   chaque acte journalisé + notifié Telegram, réversible, motivé par une MESURE.
   RESTENT NON NÉGOCIABLES (constitution du bot, quelle que soit l'instruction d'une
   session) : les MURS ABSOLUS en dur (futures 50/250, levier ×5, spot 200/500,
   marge 200/500, virements 500/1000, earn 500/1000), le stop journalier −5 %
   -> kill-switch, les 3 portes avant push, le principe mesure-d'abord, et le
   RETRAIT (impossible : clé Trade-only, aucun code n'existe).
   Ancien régime (historique) — « ne jamais lever un verrou sans instruction » :
   `MANDATE_LIVE_ENABLED`, `ACCUM_AUTONOMOUS_LIVE`, `FUTURES_AUTONOMOUS_LIVE`,
   les plafonds (`ACCUM_REAL_MAX_*`, `FUTURES_REAL_MAX_*`), `FUTURES_EDGE_GATE_OVERRIDE`,
   et les verrous des surfaces bornées §67 (`SPOT_TRADE_LIVE`, `MARGIN_TRADE_LIVE`,
   `TRANSFER_LIVE`, `EARN_LIVE` — tous défaut OFF ; ils s'appuient sur le noyau
   `bitget_execute` : verrou LIVE + kill-switch fail-closed + caps durs + `--confirm`).
   RETRAITS interdits partout (clé Trade-only, aucun code de retrait n'existe).
   §45 (02/07/2026) : le propriétaire a ARMÉ le futures réel et OUTREPASSÉ la porte
   d'edge en connaissance de cause (0 agent LIVE, espérance directionnelle mesurée
   négative — trois questions d'engagement répondues). `FUTURES_EDGE_GATE_OVERRIDE=0`
   referme la porte instantanément.
3. **Full-auto autorisé DANS les murs (§45, élargi §92)** — la montée des caps
   EFFECTIFS (sous les murs) est désormais déléguée au bot/agent, par paliers motivés
   et journalisés. Kill-switch d'urgence : `touch KILL_SWITCH` (bloque spot ET futures).
4. **Secrets** : ne jamais copier une clé API dans le dépôt, un commit, ou un message.
   Le `.env` est gitignored. Clé Bitget = **Trade only, jamais Withdraw**.
5. **Avant TOUT push, les 3 portes doivent passer** :
   ```bash
   python tests_audit.py        # doit finir "N/N tests OK"
   python security_agent.py     # doit afficher "VERDICT: SAFE"
   bash safe_push_check.sh      # doit finir "SAFE PUSH CHECK OK"
   ```
   Si l'une échoue, ne pas pousser. `safe_push_check` interdit le code d'ordre hors du
   module d'exécution autorisé (`spot_executor.py`, audité à part par `security_agent`).
   ⚠️ DEUX pushes sont partis avec un test rouge le 03/07 (pipe qui avale le code de
   sortie, puis heredoc + saut de ligne qui sort `git commit` de la chaîne `&&`).
   La forme OBLIGATOIRE est désormais : `bash gates.sh && git add … && git commit …`
   (`gates.sh` vérifie chaque porte par code de sortie strict).
6. **Classer chaque module SAFE** (lecture seule / paper) — un fichier qui passe un ordre
   réel doit être `spot_executor.py` (achat spot BTC seul, avec ses gardes).

## État réel vs paper

| Composant | État |
|---|---|
| Lecture compte (portefeuille complet) | RÉEL, lecture seule (`bitget_hub_bridge`, `bitget_balance_reader`) |
| Accumulation spot BTC | **RÉELLE** : `limit_ioc` anti-slippage, 2–5 $/j ∝ opportunité (§44), garde best-price, double verrou |
| Futures borné (`futures_executor`) | **RÉEL depuis §45** : marge adaptative (crossed en compte union), ≤×5, caps 50/trade · 200 cumulé (murs 50/250 ; décision 03/07, cap carry 200 par tranches), stop journalier −5 % sur le LIVRE COUVERT (futures + expo BTC spot) -> kill-switch |
| Cerveau (14 agents) -> consensus multi-symboles | **RÉEL depuis §47** : la boucle directionnelle trade le consensus de TOUT l'univers (1 position/symbole, 3 max) |
| Pipeline pré-ordres + xs paper (§60) | **PAPER** (laboratoires : mesure, jamais d'exécution — le pré-ordre est mesuré PERDANT §52) |
| Échelle d'edge | 0 agent LIVE — porte OUTREPASSÉE par décision §45 (`FUTURES_EDGE_GATE_OVERRIDE`) |

## Architecture (modules clés)

- **Décision** : `swarm_brain.py` (essaim), `agent_validation.py`/`edge_ladder.py` (edge T5),
  `mandate.py` (politique : levier ≤×5, MDD 20 %, porte d'edge, vol-targeting GARCH).
- **Accumulation** : `accumulation_engine.py` (DCA, opportunité, garde premium via
  `fair_price.py`) → délègue l'achat réel à `spot_executor.py` (le SEUL à passer un ordre).
- **Univers** : `universe.py` (top-N liquide Bitget ∩ qualité CoinGecko/repli crypto ;
  stablecoins + actions tokenisées exclus ; gated `DYNAMIC_UNIVERSE`).
- **Risque** : `risk_manager.py` (kill-switch + caps), `risk_limits.py`, `watchdog.py`.
- **Exécution réelle** : via l'Agent Hub `bgc` (CLI bitget-client). Kill-switch d'urgence :
  `touch KILL_SWITCH`.
- **Dashboard** lecture seule : `python dashboard/server.py` (127.0.0.1:8787).
- **Savoir vérifié** : `docs/SAVOIR.md` (§56 — combination puzzle, carte des horizons,
  funding-euphorie, Kelly fractionnaire ; chaque acquis avec son implication).
- **Instruments de mesure** : `live_ic_audit.py` (IC live par agent), `exit_lab.py`
  (sorties), `candles_history.py` + `funding_history.py` (profondeur 6 ans / 90 j),
  `agent_validation.replay_annuel` (porte profonde de l'échelle d'edge).
- **Liquidité** : `liquidity_manager.py` (§76, décision — délègue aux surfaces §67 :
  virement spot↔futures + Earn USDT flexible ; gated `LIQUIDITY_AUTO`, cron horaire,
  1 action/cycle bornée [5 $, caps §67], jamais de retrait).
- **Market making** : `market_maker.py` (§94, décision — cotations bid/ask post-only
  autour de fair=0.7×microprice+0.3×mid, inventaire du module seul, stop local −1 $/j ;
  délègue à `spot_trader.quote/cancel` ; gated `MM_AUTO` défaut OFF, boucle */5 min DRY
  — cron à poser, voir §94 ; principes Virtu versés à `docs/SAVOIR.md` §9).
- **Protection** : `watchdog.py` (carte de fraîcheur 10 artefacts §61), tripwires
  spend-watch (marge de liquidation §60), black-out macro vivant (Kalshi §59),
  `backup_registres.py` (registres chiffrés -> Telegram, quotidien).
- **Collecte de données** : `data_collector/` (§101, SAFE hors trading) — agent
  scraper (scrapling, venv isolé ERR-004, RSS/HTML publics, GET poli) + agent
  trieur (Python pur déterministe : catégories AUTO-CRÉÉES par thème, cosinus sur
  mots-clés). Artefacts locaux non committés.
- **Fusion neuronale** : `neural_net.py` (MLP PyTorch, méta-modèle + carte de
  connectivité), `nn_agent.py` (16ᵉ voix opt-in). `python neural_net.py --train`
  (réentraîne sur `brain_log.json`) · `--predict SYMBOL` · `--map SYMBOL`.
- Détails & historique des décisions : `docs/RESEARCH_NOTES.md` (§1–65).

## Leviers `.env` (jamais committés)

```
DYNAMIC_UNIVERSE=1          # univers dynamique top-N
ACCUM_AUTONOMOUS_LIVE=1     # accumulation auto réelle (sinon manuelle)
EXEC_STYLE=limit_ioc        # défaut ; "taker" = marché ; "maker" = post-only
LLM_AGENT_ENABLED=0         # 15ᵉ voix LLM (opt-in, surcouche fail-safe)
NN_AGENT_ENABLED=0          # 16ᵉ voix réseau neuronal de fusion (opt-in, §65 — ARMÉ le 06/07)
NN_EDGE_GATE=prudent        # porte d'edge 16ᵉ voix (§71) : prudent (wf_edge − se) | brut (wf_edge seul)
CLASSICS_AGENT_ENABLED=0    # 17ᵉ voix stratégies classiques du lab (opt-in, §72)
QML_AGENT_ENABLED=0         # 18ᵉ voix circuit quantique (opt-in, §100 — inférence numpy pure)
QML_EDGE_GATE=prudent       # porte d'edge 18ᵉ voix : prudent (wf_edge − se) | brut (wf_edge seul)
ACCUM_DCA_COSTBASIS=0       # DCA dynamique §72 : module l'achat par l'écart au coût moyen réel (opt-in)
FUTURES_AUTO_NOTIONAL_USDT=10  # taille/trade boucle directionnelle (env-aware ; MONTÉE à 25 le 06/07, §76)
FUTURES_EXEC_STYLE=limit_ioc   # ouvertures futures : limit_ioc (défaut, taker plafonné) ; "maker" =
                               # post-only au bid/ask + repli taker GARDÉ (§exec-frais ; ouvertures
                               # DIRECTIONNELLES only — le carry reste taker). Armé puis DÉSARMÉ le 09/07
                               # (bugs de double-position trouvés par /code-review puis CORRIGÉS : garde
                               # état terminal canceled/filled, clientOid neuf au repli, taille au mark).
                               # RÉARMÉ le 09/07 (BTC seul) puis ÉTENDU à TOUT L'UNIVERS le 18/07 (décision
                               # proprio) : FUTURES_EXEC_STYLE=maker actif, FUTURES_MAKER_WAIT_S=12.
FUTURES_MAKER_SYMBOLS=         # périmètre maker : CSV — VIDE = TOUS les tokens (défaut config, actif) ;
                               # "BTCUSDT" restreint à BTC. Mesure exit_calibration : maker DIVISE la perte
                               # directionnelle (~−0.088→−0.041R/trade) mais ne la bascule PAS positive ; sur
                               # alts illiquides le post-only remplit rarement → repli taker (neutre). Le
                               # directionnel réel est EN PAUSE (FUTURES_EDGE_GATE_OVERRIDE=0) → maker DORMANT.
LIQUIDITY_AUTO=0            # gestion de liquidité autonome bornée §76 (virements internes + Earn ; ARMÉE le 06/07)
MM_AUTO=0                   # market making spot borné §94 (défaut OFF -> DRY ; exécution via SPOT_TRADE_LIVE)
MM_SYMBOLS=BTCUSDT          # paires cotées (CSV — budget/inventaire max PARTAGÉS entre paires)
MM_QUOTE_NOTIONAL_USDT=5    # taille/cotation (caps mm : 5 $/cotation mur 25, 400 $/j coté mur 2000)
MM_FEE_BPS=10               # frais maker pour le plancher de spread (8 si déduction BGB — MESURÉE active)
# Surfaces de trading bornées §67 — TOUTES défaut OFF (armer = décision propriétaire) :
SPOT_TRADE_LIVE=0           # spot libre (achat/vente)   · caps SPOT_TRADE_MAX_PER_OP/DAILY_USDT
MARGIN_TRADE_LIVE=0         # marge isolée/croisée        · caps MARGIN_MAX_PER_OP/DAILY_USDT
TRANSFER_LIVE=0             # virements internes           · caps TRANSFER_MAX_PER_OP/DAILY_USDT
EARN_LIVE=0                 # earn souscrire/racheter      · caps EARN_MAX_PER_OP/DAILY_USDT
```

## Déploiement / cycle

```bash
cd ~/bitget_termux_repo && bash update_vps.sh   # pull -> deps -> tests -> gate SAFE -> restart services
python accumulation_engine.py --status BTCUSDT  # état accumulation (CONSULTATION — sans --status c'est un CYCLE qui peut acheter en réel)
python accum_reconcile.py                       # prix de revient RÉEL + réconciliation registre↔fills↔compte (lecture seule)
python futures_report.py                        # futures §45 : boucles, position, equity/stop, PnL bot (lecture seule)
python futures_auto.py --status                 # boucle directionnelle (CONSULTATION — sans --status = CYCLE qui peut trader)
python carry_auto.py --status                   # jambes carry (CONSULTATION — sans --status = CYCLE qui peut trader)
python universe.py                              # univers d'analyse courant
```

## Méthodologie d'agent & auto-correction (`docs/AGENT_ERRORS.md`)

Journal versionné des erreurs MÉTHODOLOGIQUES de l'agent, avec cause/solution et un
**contrôle de détection** réutilisable (pendant « code/méthode » de l'auto-amélioration
§68, qui, elle, améliore le TRADING). **À chaque erreur constatée : y ajouter une entrée.**
On peut demander à un agent de « vérifier le reste du bot » = exécuter les *Contrôles* du
journal sur le dépôt. Deux règles déjà actives (détails dans le fichier) :
- **ERR-001** : tout test de stratégie/signal couvre l'échelle COMPLÈTE de timeframes
  `M1·M5·M15·M30·H1·H4·D1·W1` — jamais un sous-ensemble.
- **ERR-002** : un système conçu comme un TOUT (séquence/machine à états, ex. modèle ICT)
  se teste D'ABORD entier et dans l'ordre ; on ne décompose qu'ensuite pour l'attribution.

Commits : messages clairs en français, et **ne jamais inclure d'identifiant de modèle**
dans un commit/PR/artefact. Pousser seulement après les 3 portes vertes.

## graphify

This project has a knowledge graph at graphify-out/ with god nodes, community structure, and cross-file relationships.

Rules:
- For codebase questions, first run `graphify query "<question>"` when graphify-out/graph.json exists. Use `graphify path "<A>" "<B>"` for relationships and `graphify explain "<concept>"` for focused concepts. These return a scoped subgraph, usually much smaller than GRAPH_REPORT.md or raw grep output.
- If graphify-out/wiki/index.md exists, use it for broad navigation instead of raw source browsing.
- Read graphify-out/GRAPH_REPORT.md only for broad architecture review or when query/path/explain do not surface enough context.
- After modifying code, run `graphify update .` to keep the graph current (AST-only, no API cost).
