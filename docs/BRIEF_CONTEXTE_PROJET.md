# Brief de contexte — Bot de trading Bitget

*Document de référence exhaustif — 10 rubriques.*
*Établi le 2026-07-05 par audit complet du VPS `srv1598293`. Aucune valeur de secret n'est reproduite (noms de variables `.env` uniquement).*

---

## Sommaire

1. [Rôle et objectif](#1--role-et-objectif)
2. [Contexte du projet](#2--contexte-du-projet)
3. [Architecture et stack technique](#3--architecture-et-stack-technique)
4. [État actuel et problèmes connus](#4--etat-actuel-et-problemes-connus)
5. [Protocole d'ingestion (instructions strictes)](#5--protocole-dingestion-instructions-strictes)
6. [Rôles, objectif et prompt de chaque agent](#6--roles-objectif-et-prompt-de-chaque-agent)
7. [Données du projet](#7--donnees-du-projet)
8. [Outils existants](#8--outils-existants)
9. [Outils manquants](#9--outils-manquants)
10. [Sources de données](#10--sources-de-donnees)
11. [Annexe — Projets annexes du VPS](#annexe--projets-annexes-du-vps)

> ⚠️ **Alerte au moment de l'audit.** Le bot est **gelé** : `KILL_SWITCH` armé automatiquement à **19:46 UTC** (2026-07-05). L'equity du livre couvert est passée de ~400 à ~239 $ vers 16:56, la halte drawdown (20 %) a refusé les ordres à 17:41, le cerveau/scan sont figés depuis 17:46. La chute (−161 $) dépasse largement le notional futures (10 $) et le book spot (~32 $) → **vraisemblablement un mouvement de capital ou un artefact de lecture d'equity, pas une perte de trading pure — à confirmer sur le compte Bitget avant toute reprise.** Détails en rubrique 4.

---

## 1 — RÔLE ET OBJECTIF

### Ce que le système est
Un bot de trading Bitget **autonome** piloté par un **cerveau déterministe en mixture-of-experts** : **14 experts** spécialisés (`swarm_brain.py`) qui lisent chacun une facette du marché et émettent un vote directionnel `vote ∈ [-1, +1]` + une confiance `confidence ∈ [0, 1]`, agrégés en un **consensus pondéré**. Le banc déterministe reste le SOCLE (gelé à 14, §62). La contrainte historique « aucun réseau de neurones » du §1 a été **LEVÉE le 06/07/2026** (décision propriétaire) : les réseaux de neurones et LLM sont désormais autorisés en **surcouches opt-in fail-safe** (LLM 15ᵉ voix, NN de fusion 16ᵉ §65, classiques 17ᵉ §72, circuit quantique 18ᵉ §100 ; toutes défaut OFF), sans jamais desserrer les murs `guards()`. La recherche (arXiv:2506.05764 : XGBoost/régression logistique égalent ou battent DeepLOB à bien moindre latence) reste une raison de garder le déterministe en socle. Le dépôt de production est `~/bitget_termux_repo`, branche de travail `claude/beautiful-heisenberg-c5aoqu`.

### Pour qui
Un **propriétaire unique** (jeanfminet). Le système est mono-propriétaire : **toute** décision structurante — armer le réel, lever un verrou, monter un plafond, changer la charte — est une **décision propriétaire explicite et datée**, consignée dans `docs/RESEARCH_NOTES.md` (journal des décisions §1 → §63).

### Le mandat
Accumuler du capital de façon **bornée et mesurée**, via trois canaux réels (état « FULL LIVE borné », décision §45 du 02/07/2026) :

- **Accumulation spot BTC** — DCA opportuniste **2–5 $/jour** proportionnel à l'opportunité (§44), jamais de vente ni de retrait, plafond ≤ 5 $/j.
- **Boucle futures directionnelle** bornée — trade le consensus du cerveau sur **tout l'univers** (1 position/symbole, 3 positions max), notional **10 $ ×2**, entrée si `|consensus| ≥ 0,35`.
- **Jambes cash-and-carry** delta-neutres (long spot BTC déjà détenu + short perp couvert) qui **moissonnent le funding**, entrée au seuil **APR net ≥ 5 %**.

### Objectif opérationnel (ROADMAP)
« Laisser les données trancher (PnL net de frais via `/futures`), monter les caps par paliers si l'exécution est propre, débrayer ce qui ne paie pas. » Le mandat de gestion est encodé dans `mandate.py` : levier ≤ ×5, MDD ≤ 20 %, porte d'edge, vol-targeting GARCH.

### Doctrine
Ce n'est **pas** un oracle de profit. La posture assumée est qu'« même le meilleur agent perd pendant les krachs ». Les résultats **négatifs** sont des acquis précieux (554 signaux réfutés §36, Hash Ribbons rejeté §42, momentum lent NO-GO en crypto §57, paires co-intégrées NO-GO §53). On ne câble jamais un signal mesuré perdant ; on ne « force » pas une stratégie hors de son régime ; on ne transpose pas mécaniquement la littérature actions vers la crypto (24/7, levier retail, cascades) — c'est le **replay 6 ans propre au dépôt** qui fait foi.

---

## 2 — CONTEXTE DU PROJET

### Historique — de Termux vers le VPS
Le projet est né comme **agent local Termux Android** (`~/bitget-agent`), pur moteur de monitoring **paper / dry-run** (`can_trade=False`, aucun ordre réel), avec un pipeline en 8 étapes (scan → outcomes → order_signal → preorder → approval → execution_gateway en DRY_RUN → bot Telegram → security_agent). L'architecture d'origine reposait sur **2 machines** : Termux (fournisseur de signaux, jamais de trading) + PC/Agent Hub (pont MCP vers l'exchange, capable de trading réel). L'état stable historique est tagué `stable-paper-dryrun-20260620` (sauvegardé dans `bitget_termux_repo~`). Le système a ensuite migré vers un **VPS Hostinger Ubuntu 24.04** (IP fixe permettant le whitelisting Bitget), devenu la machine principale de production.

### Évolution paper → réel borné (§45)
Le système est resté longtemps 100 % paper/analyse. Le passage au réel s'est fait par paliers (spot d'abord, §31/§43/§44), puis, sur **décision propriétaire du 02/07/2026 (§45)** — « je veux changer les règles et passer en full live » — le futures réel a été câblé. Trois questions d'engagement ont été posées et répondues explicitement :

- **périmètre** = carry + directionnel (en connaissance de cause : espérance directionnelle mesurée **NÉGATIVE**, 0 agent au palier LIVE) ;
- **validation** = directement réel (pas d'étape demo) ;
- **capital** = tout le solde futures.

Les avertissements ont été présentés par écrit à chaque option. Aujourd'hui : lecture compte réelle (lecture seule), accumulation spot RÉELLE, futures borné RÉEL (§45 → §47), pipeline pré-ordres / xs paper resté PAPER (laboratoire, mesuré perdant §52).

### Contraintes de conception
- **Pas de deep learning.** Si un jour on « apprend » davantage : régression logistique / gradient boosting sur de bonnes features — **jamais un deep net en premier**.
- **Mixture-of-experts déterministe.** Ensemble pondéré d'agents interprétables (chaque vote est explicable), apprentissage en ligne multiplicatif (famille Hedge / multiplicative weights), poids bornés **[0,2 ; 3,0]** et renormalisés, plancher d'exploration garanti (un agent ne tombe jamais à 0). Tout est pur, causal, testé (`tests_audit.py`).
- **EARCP** (Ensemble Adaptive Reweighting by Coherence & Performance, arXiv:2603.14651). Chaque expert est pesé par sa **performance** ET sa **cohérence** : `s_i = β·P̃_i + (1−β)·C̃_i`, softmax `η`, plancher `w_min`. **Assainie en §51** après la découverte de cinq mécanismes d'auto-amplification :
  1. cohérence « avec soi-même » → recalcul en **leave-one-out** ;
  2. min-max par lot → **bornes absolues** ;
  3. recomposition par symbole (×1,5^10 ≈ ×57/cycle) → **lissage 10 %** vers cible ;
  4. cohérence sur-pondérée → **β relevé à 0,9** (cohérence ≤ 10 % du score) ;
  5. le plus profond : l'entrée « performance » était **le poids lui-même** (boucle Hedge auto-excitée) → remplacée par un **hit-rate EWMA exogène** borné [0,3 ; 0,7].
  Doctrine confirmée par `docs/SAVOIR.md` §1 (forecast combination puzzle) : poids proches de 1,0, ne s'écartant que sur preuve durable ; sur les bords, PLUS de shrinkage vers 1,0, jamais moins.
- **Échelle d'edge (edge ladder).** Chaque agent est promu par paliers selon des preuves mesurées (`agent_validation.py`, `edge_ladder.py`). La promotion au palier **LIVE** exige **trois preuves conjointes** : coupe transversale récente positive (n effectif ≥ 120, DSR ≥ 0,90, OOS > 0), **fenêtre profonde 6 ans positive** (§54/§55, 194k bougies 2020-2026), ET confirmation d'IC en live. État actuel : **0 agent LIVE** → la porte d'edge du futures directionnel est **outrepassée** par décision propriétaire (`FUTURES_EDGE_GATE_OVERRIDE`, §45), remise à 0 = fermeture instantanée.
- **Banc GELÉ à 14 agents (§62).** Le combination puzzle et l'audit IC live montrent que la **largeur n'est pas le goulot** : on n'ajoute plus d'agent (`onchain_btc` reste dormant, réévalué seulement si un manque de canal est démontré). Corollaire : chaque composant se mesure **séparément** à l'étalon (« la somme des bonnes idées n'est pas une bonne idée », §48/§49), on exige un **plateau** de paramètre, jamais un pic de backtest (anti-cherry-picking, SAVOIR §4).

### Chronologie des décisions propriétaire
§38 (pivot vers le spot, futures suspendu) → §44 (sizing réel 2–5 $) → **§45 (full live borné câblé, override edge)** → §46 (audit multi-agents, 1er round-trip 100 % autonome, cap carry porté à 200, mode hedge) → §47 (agents en réel multi-symboles) → §48-52 (agents geometric/savant/leadlag réécrits à l'étalon) → §54-55 (porte annuelle puis porte PROFONDE 6 ans) → §56-57 (bibliothèque de savoir) → §60 (7 chantiers : sauvegarde chiffrée, exit lab, audit IC live, recommandations hebdo chiffrées) → §61 (post-mortem cerveau gelé, carte de fraîcheur) → §62 (banc gelé à 14) → §63 (cadences resserrées).

---

## 3 — ARCHITECTURE ET STACK TECHNIQUE

### Stack
- **Langage** : Python 3.12 (stdlib priorisée — le dashboard n'utilise que `http.server`).
- **Dépendances** : `numpy`, `ccxt`, `requests` — **optionnelles à dégradation propre** (le code fonctionne dégradé si `ccxt`/`numpy` absents).
- **Persistance** : **fichiers plats** (JSON, JSONL append-only, CSV), **pas de base de données**.
- **Ordonnancement** : **systemd timers** (12 unités, cf. rubrique 8).
- **Front d'exécution** : **Agent Hub** — monorepo TypeScript/pnpm publié sur npm (CLI `bgc`, serveur MCP, core signature HMAC-SHA256).
- **Sécurité repo** : hook `.claude/hooks/guard.py`, 3 portes obligatoires (`gates.sh`), skills `/run-bitget` et `/safe-push`.

### Les 5 couches

**1. Décision (le cerveau)**
- `swarm_brain.py` (37 Ko, cœur) : les 14 experts, l'agrégation par vote pondéré confiance × poids appris (EARCP), la méta-cognition (prudence anti-groupthink) et l'escompte de volatilité (CVIX).
- `brain_cycle.py` : boucle qui appelle `swarm_brain.read(sym, do_learn=True)` sur tout l'univers chaque minute, journalise et apprend.
- `agent_validation.py` / `brain_validation.py` / `edge_ladder.py` : protocole de validation T5 (Rank-IC de Spearman, PSR de Bailey/López de Prado, DSR déflaté pour le multiple testing, replication ratio arXiv:2501.03938, walk-forward purgé, coupe transversale à n effectif corrigé de la corrélation, replay 6 ans).
- `mandate.py` : la politique (levier ≤ ×5 vol-targeting GARCH, MDD ≤ 20 %, porte d'edge fail-closed, sessions actives, black-out macro).

**2. Univers & features**
- `universe.py` : top-N liquide Bitget ∩ qualité CoinGecko/repli crypto ; stablecoins + actions tokenisées exclus ; gated par `DYNAMIC_UNIVERSE`.
- Indicateurs : `technicals.py`, `pro_indicators.py`, `indicators.py`, `price_action.py`, `regime_features.py`, `microstructure.py`, `book_collector.py` (collecteur WebSocket L2), `candles_history.py`, `funding_history.py`.

**3. Exécution réelle — 2 SEULS modules**
- `spot_executor.py` : achat spot BTC d'accumulation, `limit_ioc` anti-slippage, double verrou.
- `futures_executor.py` : futures borné (marge isolée → crossed en compte union, ≤ ×5, 8 gardes dures, murs 50/250, stop journalier).
- Décideurs qui **délèguent** : `accumulation_engine.py` (spot), `futures_auto.py` (directionnel), `carry_auto.py` + `carry_monitor.py` (carry).

**4. Risque & sécurité**
- `risk_manager.py` (kill-switch partagé + caps), `risk_limits.py`, `risk_state.py`, `position_sizer.py`, `regime_gate.py`.
- `config.py` : source unique des garde-fous chiffrés et des verrous.
- `watchdog.py` (carte de fraîcheur 10-11 artefacts), `security_agent.py` (porte de push), `prompt_guard.py` (anti prompt-injection LLM), hook `guard.py`.

**5. Observabilité & I/O**
- Dashboard lecture seule (`dashboard/server.py`, 127.0.0.1:8787).
- Bot Telegram (`telegram_command_bot.py`, ~50 commandes lecture seule ; `telegram_notifier.py` résumé 15 min).
- Assistant LLM (`assistant/` : `/ask`, vision de charts).
- Rapports (`futures_report`, `accum_reconcile`, `revue_hebdo`, `live_ic_audit`, `exit_lab`, `journal_de_bord`…) et sauvegarde chiffrée (`backup_registres.py`).

### Diagramme de flux (chemins réels)
```
swarm_brain (14 experts, 1 min) ─consensus─> futures_auto ─> futures_executor ─[bgc]─> Bitget (futures réel)
accumulation_engine (opportunité) ──────────> spot_executor ─[bgc]─────────────> Bitget (spot réel)
carry_monitor (APR net) ───────> carry_auto ─> futures_executor (+ spot détenu) ─> Bitget (carry réel)

        bordé en permanence par : KILL_SWITCH · double verrou · murs 50/250 · stop −5 % · MDD 20 %
```

### Pipeline paper (laboratoire — jamais d'exécution réelle)
```
journal_scanner ─> outcome_state ─> order_signal_engine ─> preorder_engine [GATE cerveau]
   ─> preorder_guard ─> preorder_approval ─> execution_gateway (DRY_RUN_ONLY, real_order_sent=false)
   ─> paper_positions ─> paper_position_reconciler ─> rapports (risk / report / paper_report)
```

### Agent Hub (`agent_hub/`) — le pont d'exécution `bgc`
Monorepo pnpm (TypeScript) qui connecte des assistants IA à Bitget : c'est les **MAINS** (capable de trader) tandis que le dépôt Python est le **CERVEAU**. Packages : `bitget-client` (CLI `bgc`, sortie JSON — le pont d'exécution réel), `bitget-core` (signature HMAC, rate-limiting, mapping API), `bitget-mcp` (serveur MCP), `bitget-skill` + `bitget-skill-hub` (5 skills d'analyse). 36 outils par défaut (spot 13 + futures 14 + account 8). Sécurité : credentials par **variables d'environnement seulement**, flag `--read-only`, confirmation explicite avant toute écriture. Le module Python `bitget_hub_bridge.py` (SAFE) n'appelle `bgc` **qu'en lecture** (fills, soldes) et soumet chaque décision à `mandate.py`.

---

## 4 — ÉTAT ACTUEL ET PROBLÈMES CONNUS

### État (2026-07-05 ~20:03 UTC)
- **Mode nominal** : FULL LIVE borné (§45). **Actuellement GELÉ** — `KILL_SWITCH` présent, armé **19:46:29** aujourd'hui → spot ET ouvertures futures bloqués ; seules les réductions/fermetures restent permises.
- **Branche** `claude/beautiful-heisenberg-c5aoqu`, à jour avec origin, arbre propre. **Dernier commit** `228f832` (« Telegram : /bord + /audit »).
- **Equity réelle** : livre suivi ; `open_equity` du jour **401,25 $** (parti de ~206 $ le 03/07, +191 $ d'apport de capital le 04/07 ; 306 points intraday).
- **Edge mesuré : plat à négatif.** `validation_report.json` (n ≈ 2390, boucle multi-symboles) : **aucun agent n'a d'IC live positif significatif** ; **les 14 hit-rates directionnels live sont < 0,46** (tous sous 50 %). La porte d'edge affiche « 0 agent LIVE » et est franchie par `FUTURES_EDGE_GATE_OVERRIDE=1` (décision §45).
- **Ce qui tourne** : collecteur microstructure VIVANT (écrit à 20:02, ~1 min) ; timers `bitget-brain`/`bitget-scan`/`bitget-watchdog` actifs. **Mais** `brain_log.json`, `brain_log_history.jsonl`, `signals_journal.csv`, `futures_auto_journal.jsonl` sont **figés à 17:46:40** — depuis l'armement du kill-switch, la `ConditionPathExists`/`ExecCondition` des services brain+scan les fait sauter à chaque tic (comportement attendu sous kill-switch).

### ⚠️ Incident en cours — à investiguer AVANT de lever le kill-switch
Chronologie reconstituée (`futures_real_ledger.json`, mtimes, systemd) et vérifiée :

| Heure UTC | Événement |
|---|---|
| 16:25 → 16:45 | equity du livre couvert ≈ **400 $** |
| ~16:56 | chute à **≈ 239,5 $** (**≈ −40 % / −161 $ intraday**), puis plateau à ~239,5 $ |
| 17:41 → 17:44 | 3 ordres futures **REFUSÉS**, motif journalisé `halte drawdown (40,45 % ≥ MDD toléré 20 %)` |
| 17:46:40 | cerveau + scan **cessent d'écrire** (la boucle qui porte le stop *immédiat* meurt) |
| 19:46:28 | `accum_spend_watch` (tripwire horaire) détecte le franchissement du stop −5 % et **arme le KILL_SWITCH** (~2 h après la chute) |

**À trancher par le propriétaire.** La baisse ~400 → 239 $ (−161 $) **dépasse largement** le notional futures (10 $ ×2) et le book spot (~32 $) → ce n'est **probablement pas** une perte de trading pure mais un **mouvement de capital / artefact de lecture d'equity** (p. ex. virement interne futures→spot d'un montant proche de l'apport de 191 $ de la veille), à **confirmer sur le compte Bitget** avant tout redémarrage. Fait établi : le stop et la halte MDD ont bien réagi ; la vraie fragilité est le **délai de 2 h** (le stop immédiat vit dans une boucle qui peut mourir).

### Problèmes connus (documentés)
- **§61 — cerveau gelé 4,7 h.** `NameError` sur `_cfg` avalé par un `try/except` unique → poids figés à 1,0, boucle aveugle (fail-closed, zéro trade). Verrous posés : import module-level, learn/record séparés avec exceptions imprimées, smoke-test `learn()` bout-en-bout, watchdog surveille la fraîcheur du brain_log (>20 min → alerte). **Un gel s'est reproduit ~2 h aujourd'hui** → la garantie « rien d'aveugle » du §61 est à re-vérifier.
- **Deux pushes rouges le 03/07.** Pipe qui avale le code de sortie, puis heredoc + saut de ligne sortant `git commit` de la chaîne `&&`. Correctif : forme obligatoire `bash gates.sh && git add … && git commit …` (codes de sortie stricts).
- **§46 (audit P0).** Signature `_atr` cassée (le SL réel n'a jamais été basé ATR — repli 1,5 % silencieux) ; doublon config `FUTURES_REAL_MAX_*` ; halte drawdown du mandat inerte sur le chemin réel ; `/run_once` pouvait déclencher un cycle réel depuis le chat (désactivé). **Tous corrigés.**
- **§52.** Le pipeline **pré-ordre est mesuré PERDANT** → maintenu en PAPER, jamais exécuté.

### Experts négatifs / dépondérés
- **IC live négatif** : `technicals` −0,040 (t −1,95, le pire), `carry` −0,023 (t −1,14), + savant/derivs/structure légèrement < 0. `macro`, `sentiment`, `flows` à IC ≈ 0 (canaux muets).
- **§62 (audit des 3 négatifs)** : `carry` −0,14, `derivs` −0,18, `liquidations` −0,18 à 1 h, **aggravés à −0,40 (t −10,8) à 4 h** sur 2,6 j de live. Verdict : famille contrarian qui vote LONG en continu dans un marché baissier (Fear & Greed 21) ; formulations jugées intactes, sous-perf attribuée au régime → laissées à la couche adaptative. **À rouvrir si la négativité persiste plusieurs semaines.**
- **Poids au plancher 0,2** : `divergent` (hit-rate 0,438), `simons` (seul avec `wfa_pass=false`, wfa_frac 0,4, IC xs −0,032), `geometric` (hit-rate 0,329, le plus bas).
- **Tension notable** : `carry` (poids 1,645) et `technicals` (1,238) restent fortement pondérés via leurs hit-rates élevés (0,635 / 0,595) **alors que leur IC live est négatif** — le poids suit le hit-rate, pas l'IC.

### Fragilités structurelles
- Edge directionnel négatif mais **porte franchie** (`FUTURES_EDGE_GATE_OVERRIDE`) — assumé §45, mais c'est la fragilité de fond : on trade en réel un signal d'espérance mesurée négative.
- `exit_lab` : seulement 4 fermetures réelles (< 10) → impossible de conclure sur les conventions SL 1,5·ATR / RR 2 (le paper suggère WR 33,5 % / ratio TP-SL 0,504).
- Verdict directionnel **bloqué avant 30 fills** (§60) → échantillon réel encore insuffisant.

---

## 5 — PROTOCOLE D'INGESTION (INSTRUCTIONS STRICTES)

*Tout agent (humain ou IA) travaillant sur ce dépôt DOIT respecter ces règles — littéralement.*

### 5.1 Les 6 règles d'engagement (CLAUDE.md, révisées 02/07/2026, §45)
1. **Argent réel en jeu.** Deux modules — et SEULEMENT eux — passent des ordres réels :
   - `spot_executor.py` : achat spot BTC d'accumulation, ≤ 5 $/j, jamais de vente/retrait ;
   - `futures_executor.py` : futures BORNÉ — marge ISOLÉE, levier ≤ ×5, murs en dur **50 $/trade** et **250 $ cumulé** (env/config peuvent ABAISSER, JAMAIS dépasser), stop de perte journalier (−5 % → kill-switch), jamais de retrait/virement/annulation.
   Le cerveau / scan / pré-ordres restent paper hors de ces deux modules.
2. **Ne JAMAIS lever un verrou sans instruction explicite du propriétaire** : `MANDATE_LIVE_ENABLED`, `ACCUM_AUTONOMOUS_LIVE`, `FUTURES_AUTONOMOUS_LIVE`, plafonds `ACCUM_REAL_MAX_*` / `FUTURES_REAL_MAX_*`, `FUTURES_EDGE_GATE_OVERRIDE`. Mettre `FUTURES_EDGE_GATE_OVERRIDE=0` referme la porte d'edge instantanément.
3. **Full-auto autorisé DANS les murs (§45)** — la montée des caps effectifs reste une décision propriétaire explicite, par paliers, si l'exécution est propre. **Kill-switch d'urgence : `touch KILL_SWITCH`** (ou `TRADING_HALT=1`) → bloque spot ET futures.
4. **Secrets.** Jamais une clé API dans le dépôt, un commit ou un message. Le `.env` est gitignored (permissions `-rw-------`). Clé Bitget = **Trade only, jamais Withdraw**. Ne jamais afficher le contenu du `.env` (`check_env.py` / `/envcheck` ne rapportent que « OK (n car.) » ou « MANQUANT »). Piège d'écriture : le mot `transfer` (et « transfert ») est scanné comme dangereux → écrire « flux » / « virement » dans le code scanné ; capturer le vrai code retour (`cmd; RC=$?`), pas `PIPESTATUS`.
5. **Avant TOUT push, les 3 portes doivent passer** (s'arrêter à la première rouge) :
   ```bash
   python tests_audit.py      # doit finir "N/N tests OK"
   python security_agent.py   # doit afficher "VERDICT: SAFE"
   bash safe_push_check.sh    # doit finir "SAFE PUSH CHECK OK"
   ```
   **Forme OBLIGATOIRE** (née des 2 pushes rouges du 03/07) : `bash gates.sh && git add … && git commit …`. Push seulement sur la branche `claude/…`, **jamais `main`**, et **jamais d'identifiant de modèle** dans le commit/PR.
6. **Classer chaque module SAFE** (lecture seule / paper). Un fichier qui passe un ordre réel doit être `spot_executor.py` ou `futures_executor.py`, audités à part par `security_agent`.

### 5.2 Les 3 portes en détail
- **`gates.sh`** (`set -uo pipefail`) : porte 1 `tests_audit`, porte 2 `security_agent` (grep `VERDICT: SAFE`), porte 3 `safe_push_check` ; la moindre rouge → `exit 1`, et le `git commit` n'est jamais atteint.
- **`safe_push_check.sh`** en 5 étapes : (1) git status ; (2) blocage des fichiers interdits SUIVIS par git (`.env`, `*.log`, `*.jsonl`, `*.csv`, `*.pid`, `paper_positions.json`, `pending_orders.json`, `telegram_offset.txt`) ; (3) recherche de VALEURS de secret en dur (autorise `os.getenv(...)`, doc, placeholders) ; (4) grep des fonctions dangereuses sur `*.py` en excluant `security_agent.py`, `getagent_audit.py`, `tests_audit.py`, `spot_executor.py`, `futures_executor.py` ; (5) relance tests_audit + security_agent. Mots-clés dangereux : `place_order`, `open_long`, `open_short`, `close_position`, `cancel_order`, `change_leverage`, `set_leverage`, `transfer`, `withdraw`, `send_order`, `create_order`, `submit_order`, `market_order`, `limit_order`…
- Le skill **`/safe-push`** applique les portes mais **ne pousse jamais** automatiquement : le push reste une action explicite du propriétaire.

### 5.3 Le hook `guard.py` (PreToolUse, Bash uniquement)
Garde-fou local sur la machine aux vraies clés (`.claude/settings.local.json` le branche en `PreToolUse` matcher `Bash`). Il **BLOQUE (exit 2)** quatre familles d'actions ; tout le reste passe (exit 0) ; entrée inattendue → **fail-open** (ne casse jamais la session) :
1. `spot_executor.py … --confirm` → achat spot BTC réel.
2. `accumulation_engine.py` lancé **en script** (`python … fichier` ou `./fichier`) → chemin d'achat réel (l'import lecture seule `python -c` reste OK).
3. `bgc` avec un verbe d'ordre/transfert/retrait (`place_order`, `open_long`, `open_short`, `close_position`, `cancel_order`, `change_leverage`, `set_leverage`, `transfer`, `withdraw`…).
4. `git add … .env` → fuite de secret (`.env.example` reste autorisé).

### 5.4 Principe « on n'exécute jamais pour voir » (skill `/run-bitget`)
On observe via le dashboard lecture seule (`127.0.0.1:8787`, `/healthz`, `/api/state`) et les CLI de consultation (`--status`). **Piège documenté** : `python accumulation_engine.py BTCUSDT` (SANS `--status`) exécute un CYCLE qui peut acheter en réel ; idem `futures_auto.py` / `carry_auto.py` sans `--status`.

### 5.5 Interdits durs et invariant
- **Interdits durs** : jamais retrait, virement, margin trading, vente spot, annulation d'ordre ; pas de secrets dans Git ; pas de `can_trade=True` sur les agents du cerveau (ils DÉCIDENT, les exécuteurs exécutent) ; pas de dépassement des murs 50/250 ni du stop −5 % sans décision propriétaire.
- **Frontière invariante** : *ce qui apprend ≠ ce qui protège.* L'apprentissage en ligne n'ajuste QUE les poids de vote (`brain_weights.json`) ; les limites de risque (kill-switch, caps, perte journalière, distance de stop ≥ k·ATR) viennent de l'env/config et ne sont JAMAIS apprises. Le risque MODULE la conviction, il ne la BRIDE pas (CVIX : `scale` jamais < 0,6).

---

## 6 — RÔLES, OBJECTIF ET PROMPT DE CHAQUE AGENT

Le système comporte **deux populations d'agents distinctes** :
- **(A) les 14 experts du cerveau** — heuristiques déterministes votantes ; comme il n'y a **aucun LLM**, le « prompt » d'un expert = sa **spécification déterministe** (entrées, règle/formule, sortie) ;
- **(B) les 20 agents opérationnels** du manifeste (`agents_manifest.py`), tous `can_trade=False`.

### A. Les 14 experts du cerveau (`swarm_brain.py`)
Contrat commun : `agent(symbol) → {vote ∈ [-1,+1], confidence ∈ [0,1], note}`, fail-safe (toute exception → vote 0). Horizon de jugement `HORIZON_S = 3600 s`. Votes récoltés en parallèle (ThreadPoolExecutor 8 workers).

| # | Expert | Objectif | « Prompt » = logique déterministe (entrées → règle → vote) | Fichiers |
|---|---|---|---|---|
| 1 | **orderflow** | Pression acheteur/vendeur immédiate | Carnet L2 (20 niveaux) + tape. `imbalance=(bid_vol−ask_vol)/total`, `cvd`. `vote=clamp(imbalance·2 ± 0,3·signe(cvd))`, `conf=min(\|imb\|·1,5 ; 1)` | `order_flow.py`, `microstructure.py`, `bitget_market_data.py` |
| 2 | **technicals** | Tendance + momentum classiques | EMA20/50, RSI14, biais volume (15 m). `+0,5` si ema20>ema50 ; RSI **contrarian** (`+0,3` si <35, `−0,3` si >65) ; `+0,4·clamp(vb/10)`. conf 0,6 | `technicals.py`, `indicators.py`, `pro_indicators.py` |
| 3 | **macro** | Risk-on/off TradFi + posture monétaire | Régime VIX/2s10s/DXY (FRED, cache 30 min) + framework 6 indicateurs (core PCE, chômage/NFP, taux réel TIPS, DXY, VIX, poids 0,30/0,20/0,20/0,20/0,10) → biais BTC = −posture hawkish. Fusion pondérée par confiance | `macro_context.py`, `macro_regime.py`, `macro_data.py` |
| 4 | **sentiment** | Fader la peur/euphorie de foule | Fear & Greed Index (alternative.me, cache 15 min). `vote=clamp((50−v)/50)` **contrarian**, `conf=\|50−v\|/50` | `sentiment_index.py` |
| 5 | **derivs** | Longs/shorts surchargés | Funding 8 h pondéré-OI agrégé (Binance+Bybit+Bitget, cache 5 min). `vote=clamp(−f·2000)` (funding+ → short contrarian) | `aggregated_derivs.py` |
| 6 | **liquidations** | Aimants de liquidité | Modèle prix×levier×OI (pas un flux exchange). `skew.net ∈ [-1,1]` pondéré par proximité ±8 %. `vote=clamp(net)` (pools shorts au-dessus = aimant haussier) | `liquidations.py` |
| 7 | **divergent** | Anticiper le retournement (early-warning) | Critical slowing down (Scheffer 2009). 60 closes 15 m, débruitage Savitzky-Golay. Mean-reversion douce (z-score) + divergence prix/RSI (pentes de signes opposés) + instabilité (var-ratio + Δautocorr lag-1). `vote=clamp(direction·(1+0,6·instabilité))` + nudge ESM ±0,2 | `indicators.py`, `esm.py`, `regime_features.py`, `price_action.py` |
| 8 | **structure** | SMC (BOS/CHoCH) + Volume Profile | 120 bougies 15 m. BOS `+0,5·dir` (0,2 si faux breakout/stop hunt), CHoCH `+0,4·dir`, sinon `+0,2·biais` ; fade hors Value Area ±0,3 ; chandeliers (doji/hammer/engulfing) confirmateurs `+0,1` | `price_action.py`, `pro_indicators.py` |
| 9 | **simons** | Medallion crypto (régimes cachés + arb stat) | 160 closes 15 m. **HMM gaussien k=3** (Baum-Welch/Viterbi, init déterministe par quantiles). `range` → réversion OU `vote=−tanh(z·0,8)` (achète faiblesse) ; `stress` (vol_ratio>1,8) → retrait (vote 0) ; `trend` → suivi léger. Kelly fractionnaire indicatif (ne dimensionne aucun ordre) | `simons_agent.py` |
| 10 | **savant** | Ruptures de symétrie microstructure | 72 bougies, tenseur D=5 `[ret, \|ret\|, CLV, amplitude, volume]`. Anomalie de **Mahalanobis** → `symmetry_break sb`. Vote actif seulement si `sb≥0,55` : `vote=fade(dernier ret)·min((sb−0,55)/0,45 ; 1)·0,6` | `savant_agent.py` |
| 11 | **geometric** | Régime de queue + toxicité d'ordre supérieur | 160 closes + microstructure L2. Indice de Hill α, Hurst DFA, distance W1 → **non-euclidien** (α≤2,2, suivi tendance) / **euclidien** (α≥3,5, réversion). Toxicité (Eldan-Gross ⊕ sauts BNS ⊕ markout réel) : `vote=clamp(base·(1−tox))` | `geometric_agent.py` |
| 12 | **flows** | Dry powder marché-large | Offre de stablecoins (DefiLlama, momentum 7/30 j, cache 1 h). `vote=0,6·tanh(pct7/0,5)+0,4·tanh(pct30/2,0)`, conf **plafonnée 0,5** (humilité) | `flows_agent.py`, `stablecoin_flow.py` |
| 13 | **carry** | Positionnement dérivés contrarian (3D) | funding z-score historique + foule L/S (comptes Bitget) + basis perp-spot. `vote=clamp(0,5·c_funding+0,35·c_foule+0,15·c_basis)` (×1,5 si `\|funding\|≥0,05 %/8h`), `conf=min(0,6 ; \|vote\|·1,2)` | `carry_agent.py`, `derivs_positioning.py` |
| 14 | **leadlag** | BTC → alts contrarian (§52) | 90 closes alt + 90 BTC. `z=Σ(rendements BTC 8 barres)/(σ64·√8)`, `vote=−tanh(z/2)` (fade du meneur). **BTC vote 0**. (IC 1 an tombe à +0,014 → pesé par hit-rate) | `leadlag_agent.py` |

**Agrégation & consensus** (`aggregate`) :
```
num = Σ vote_i · conf_i · w_i        den = Σ conf_i · w_i
consensus = num / den
bias = LONG  si consensus >  0,2 ;  SHORT si consensus < −0,2 ;  NEUTRE sinon
conviction = |consensus|
```
- Seuil **±0,2** (zone morte NEUTRE). Poids `w_i ∈ [0,2 ; 3,0]`.
- **Méta-cognition** : groupthink si `agreement ≥ 0,85 ET |consensus| ≥ 0,4` → `prudence = 0,8`.
- **Escompte de volatilité** (CVIX) : ratio vol court/long → `scale` = 1,0 / 0,85 / 0,6, jamais < 0,6.
- `conviction_ajustée = conviction · prudence · scale`.

**Apprentissage EARCP** (`learn`) : `P̃ = hit-rate EWMA exogène` (α=0,05, `brain_hitrates.json`, borné [0,3 ; 0,7]) ; `C̃ = cohérence leave-one-out` ; `s = β·P̃ + (1−β)·C̃` (β=0,9) ; `w ∝ exp(η·s)` (η=5, plancher `w_min`) ; **lissage 10 %** vers cible ; clamp [0,2 ; 3,0] ; priors d'edge advisory (`prior^0,5`, débrayable `BRAIN_EDGE_PRIORS=0`). Persistance : `brain_weights.json`.

**Échelle d'edge** (`edge_ladder.py`, priors advisory sur l'EARCP) :

| Palier | Critère | Prior de poids |
|---|---|---|
| **LIVE** | replay (DSR≥0,90, n≥120, OOS>0) ET confirmation live (n≥60, IC-t≥2) ET annuel (IC>0) | ×1,5 |
| **PROBATION** | DSR≥0,50 et n≥30 (ou replay OK sans confirmation) | ×1,0 |
| **PAPER** | DSR≥0,10 | ×0,6 |
| **NEGATIVE** | sinon (ou absent) | ×0,3 |

`mandate.futures_live_allowed(agent)` applique **le même critère LIVE** comme **porte du réel** (fail-closed). État : **0 agent LIVE**, porte outrepassée (§45).

### B. Les 20 agents opérationnels (`agents_manifest.py`, tous `can_trade=False`)

**Pipeline paper (laboratoire) :**

| Agent (id) | Fichier | Objectif / rôle concret |
|---|---|---|
| Market (`market_agent`) | `journal_scanner.py` | Scanne l'univers, calcule EMA9/21, RSI14, ATR14, score + décision, porte régime-aware, écrit `signals_journal.csv`. « ANALYSE SEULEMENT » |
| Outcome (`outcome_agent`) | `outcome_state.py` | Suit les signaux, détecte TP/SL (long ET short), écrit `open_outcomes_state.csv` + `final_outcomes_journal.csv` |
| Order Signal (`order_signal_agent`) | `order_signal_engine.py` | Analyses → cartes signal + confluence advisory (carnet/CVD/macro), `order_signals_report.txt`. « PROPOSITION UNIQUEMENT » |
| Preorder (`preorder_agent`) | `preorder_engine.py` | Fige ≤5 pré-ordres verrouillés ; GATE cerveau (`swarm_brain.peek`, peut seulement réduire) + vol-target + caps portefeuille. `pending_orders.json` |
| Preorder Guard (`preorder_guard_agent`) | `preorder_guard.py` | Bloque les pré-ordres si portefeuille en OBSERVATION (≥3 négatives) |
| Preorder Approval (`preorder_approval_agent`) | `preorder_approval.py` | Approuve/refuse en **simulation** (`APPROVED_SIMULATION`), journalise |
| Execution Gateway (`execution_gateway_agent`) | `execution_gateway.py` | Simule l'exécution en `DRY_RUN_ONLY`, risk-gate fail-closed, `real_order_sent=false`, crée la position paper |
| Paper Position (`paper_position_agent`) | `paper_positions.py` | Tient les positions paper (`PAPER_ONLY_NO_REAL_ORDER`, anti-doublon) |
| Paper Reconciler (`paper_position_reconciler_agent`) | `paper_position_reconciler.py` | Clôture paper CLOSED_TP / CLOSED_SL / AMBIGU |
| Paper Report (`paper_report_agent`) | `paper_report.py` | Résumé lecture seule des positions paper |

**Rapports & risque :** Risk (`risk_agent` / `compact_report.py` — classe le risque, suggère une action), Report (`report_agent` / `state_report.py`), Balance (`balance_agent` / `bitget_balance_reader.py` — lit le solde Bitget signé HMAC-SHA256, lecture seule).

**Orchestration :** Control (`agent_control.py` — enchaîne le cycle dans le bon ordre), Loop (`agent_loop.py` — cadence + `agent_loop.pid`), Hub (`agent_hub.py` — tableau de bord CLI), Telegram (`telegram_command_bot.py` — filtré `ALLOWED_CHAT_ID`, anti-flood, anti-injection).

**Sécurité & garde :** Security (`security_agent.py` — porte de push : vérifie `can_trade=False` partout, scanne ~80 fichiers, audite les 2 exécuteurs, `VERDICT: SAFE`), Config Guard (`config_guard_agent.py` — table `SAFE_LIMITS`, valide sans appliquer), GetAgent Audit (`getagent_audit.py` — scanne le skill externe). **Hors manifeste mais dans le périmètre garde** : `watchdog.py` (carte de fraîcheur, peut armer le kill-switch, ne redémarre jamais) et `prompt_guard.py` (anti prompt-injection LLM, redact_secrets).

> **Distinction cardinale.** Ces 20 agents **observent, mesurent, simulent** ; SEULS `spot_executor.py` et `futures_executor.py` **agissent** (hors manifeste, audités à part). Les boucles `futures_auto` / `carry_auto` / `accumulation_engine` **décident** puis délèguent aux exécuteurs. Le point terminal du pipeline paper (`execution_gateway`) est un `DRY_RUN_ONLY` : tous ses artefacts portent `real_order_sent=false`.

---

## 7 — DONNÉES DU PROJET

*Artefacts runtime dans `~/bitget_termux_repo` — preuves d'activité réelle et traçable.*

### Registres réels (argent en jeu)
- **`futures_real_ledger.json`** (50,7 Ko) — le registre le plus important. **36 événements** : **25 `FUTURES_REAL`** (`real_order_sent=true`, chacun avec l'`orderId` renvoyé par `POST /api/v2/mix/order/place-order`), 4 `FUTURES_REAL_FAILED`, 2 `FUTURES_DRY_RUN`, 5 `FUTURES_REFUSED` (verrous). Du **02/07 19:10** au **05/07 13:38 UTC**, sur BTCUSDT, ×2, notional 4–10 $, avec presets stop/TP. Contient aussi `equity_journal` (206 → 398 → 401 $), `daily_loss_state`, 306 points d'equity intraday. Agents ayant tradé en réel : `validation` (premiers essais) puis `auto_dir` (boucle §47).
- **`accumulation_real_ledger.json`** (1,1 Ko) — **7 achats spot BTC réels** (6 × 5,00 $ + 2,27 $), depuis le 27/06 ; les derniers enrichis du contexte de décision (score, prix, premium, RSI, F&G).
- **`.carry_journal.json`** (60 Ko) — 78 snapshots funding/carry (mesure, aucun ordre).
- **`accumulation_ledger.json`** (279 o) — registre legacy agrégé.

### Journaux (flux d'événements)
- **`brain_log_history.jsonl`** (9,76 Mo, **26 157 lignes**) — historique complet des votes des 14 agents (ts, symbol, price, votes{14}, consensus, evaluated). Fenêtre 03/07 05:52 → 05/07 17:46. `brain_log.json` (898 Ko, fenêtre glissante 2 400).
- **`signals_journal.csv`** (2,6 Mo, **22 340 signaux**) — timestamp, symbol, price, decision, score, ranking, rsi, atr%, ema_distance, status, side, entry, SL, TP, notional, implied_leverage, rejection_reason.
- **`microstructure_history.jsonl`** (5,4 Mo, **34 719 snapshots** carnet) — ts, symbol, mid, ofi, queue_imbalance, trade_sign, spread_bps. + `.microstructure_buffer.json` (buffer vivant seconde/seconde).
- **`futures_auto_journal.jsonl`** (1,2 Mo, **5 476 décisions**) — ts, boucle (auto_dir/carry), consensus, apr_net_pct, position, action, raison, executed.
- **`final_outcomes_journal.csv`** (46,8 Ko, **241 issues** clôturées TP/SL/AMBIGU). **`open_outcomes_state.csv`** (12 positions/signaux suivis).
- **`preorder_guard_journal.jsonl`** (201 entrées, `real_order_sent` toujours **false**). **`xs_paper_journal.jsonl`** (75, PnL paper négatif assumé ~ −16/−18 $). **`market_timing_history.jsonl`** (7).

### États (instantanés courants)
- **`brain_weights.json`** (poids adaptatifs des 14 agents) + **`brain_hitrates.json`** (hit-rates EWMA).
- **`.runtime_cache.json`** (356 Ko) — cache TTL macro (VIX 16,59, EUR/USD 1,1438, F&G 23 « Extreme Fear », régime RISK_ON) **et fills/fees réels Bitget** (billId, fee, profit → trace comptable).
- **`pending_orders.json`** (5 ordres **REJECTED** « KILL_SWITCH actif », equity_source `REAL_BITGET_EQUITY` 205,95 $), **`.futures_pos_state.json`** (0 position ouverte), **`paper_positions.json`** (vide, `PAPER_ONLY`), **`.xs_paper_etat.json`**, **`.accum_spend_alert.json`**.

### Savoir & rapports
- **`knowledge.json`** (80 Ko, **70 entrées** de savoir extrait — id, category, action, target, source, body).
- **`validation_report.json`** (8,5 Ko, échelle d'edge T5 par agent : n, ic, ic_t, hit, sharpe, psr, dsr, oos_sharpe, wfa_pass — `savant` en tête ic 0,146).
- **`order_signals_report.txt`**, **`docs/SAVOIR.md`** (combination puzzle, carte des horizons, funding-euphorie, Kelly fractionnaire).

### Historiques (`data_history/`)
- **Bougies OHLCV 6 ans** : BTC/ETH/XRP en 1D ≈ 2 161 bougies (depuis 2020-07) et 1H ≈ 50 202 (depuis 2020-10) ; SOL 1 788 / 43 142. Base de la porte de validation « 6 ans ».
- **`FUNDING_BTCUSDT.json`** (271 points, ~90 j). `logs/` quasi vide (1 archive gzip).

### Ce que ces données prouvent
1. **Des trades réels existent, horodatés et traçables** : 25 ordres futures (chaque réponse contient un `orderId`) + 7 achats spot ; fees/fills réels cachés dans `.runtime_cache.json`.
2. **L'equity réelle est suivie et a bougé** : ~206 → ~401 $ (saut = apport de capital), 306 points intraday ; le stop journalier −5 % s'appuie sur ce livre.
3. **Le bot tourne en continu (~1 min)** depuis le 27/06 : 26 157 votes, 34 719 snapshots micro, 22 340 signaux, 5 476 décisions futures.
4. **La séparation réel/paper est vérifiable** : seuls les 2 ledgers portent `real_order_sent=true` ; les laboratoires restent paper.
5. **Au moment de l'inventaire, le trading est GELÉ** (KILL_SWITCH présent, pending_orders REJECTED).

---

## 8 — OUTILS EXISTANTS

### Famille 1 — Observabilité, rapports & audit (CLI lecture seule, SAFE)

| Outil | Rôle |
|---|---|
| `futures_report.py` | Réconciliation du futures réel §45 : décisions boucle vs fills Bitget (PnL réalisé, frais) vs état compte (equity, stop). Sert `/futures` |
| `accum_reconcile.py` | Prix de revient RÉEL (VWAP des fills, frais inclus), PnL latent, réconciliation 3 sources (registre ↔ fills ↔ compte). Sert `/accum_reel` |
| `accum_spend_watch.py` | Tripwire horaire : alerte si dépense spot > 5 $/j **et** évalue le stop de perte futures — **peut armer le kill-switch** |
| `revue_hebdo.py` | Revue hebdo compilée (accumulation, futures, carry APR médian, bornes poids, runway). `--send` → Telegram |
| `stats_report.py` | Stats des outcomes finalisés (TP/SL, ratio, par symbole/sens). Sert `/stats` |
| `live_ic_audit.py` | Audit permanent de l'IC live par agent (a démasqué la saturation EARCP §51). Sert `/audit` |
| `exit_lab.py` | Laboratoire des sorties : MFE/MAE en unités d'ATR sur paper + trades réels (advisory) |
| `equity_curve.py` | Courbe d'equity réalisée → alimente `mandate.drawdown_halt()` |
| `journal_de_bord.py` | Journal de bord — événements réels notables (ordres, DCA, fermetures, échecs). Sert `/bord` + dashboard |
| `system_health.py` | Bilan de santé (fichiers, fraîcheur, config booléenne, pause). Ligne `HEALTH: OK/DEGRADED` |
| `backup_registres.py` | Sauvegarde chiffrée AES-256-CBC/PBKDF2 des registres → DOCUMENT Telegram (`BACKUP_PASSPHRASE`) |
| `git_version.py` | Version Git lecture seule (rev-parse, describe, log, status). Sert `/git_version` |
| `watchdog.py` | Surveillance boucle (`agent_loop.pid` + `/proc` + fraîcheur scan) + carte de fraîcheur 10 artefacts. `--alert` → Telegram. Ne redémarre jamais |
| `compact_report.py` / `journal_report.py` / `outcome_report.py` / `state_report.py` | Rapports compacts / signaux / outcomes / état courant |

Instruments connexes : `candles_history.py` + `funding_history.py` (profondeur 6 ans / 90 j), `agent_validation.replay_annuel` / `brain_validation.py` (porte profonde), `edge_ladder.py`.

### Famille 2 — Telegram (`telegram_command_bot.py`, ~50 commandes, filtré `ALLOWED_CHAT_ID`)
- **Système** : `/start`, `/help`, `/status`, `/config`, `/config_guard`, `/hub`, `/agents`, `/security`, `/getagent_audit`, `/git_version`, `/system_health`, `/watchdog`, `/bord`, `/audit`, `/stats`, `/envcheck` (présence des clés, jamais les valeurs).
- **Marché / microstructure** : `/orderflow`, `/macro`, `/confluence`, `/price`, `/news`, `/deriv`, `/poly`, `/liq`, `/calendar` (`/eco`), `/arb`, `/tradfi`, `/cross`, `/feargreed`, `/defi`, `/rugcheck`, `/dexsearch`, `/chart` (dessine et envoie l'image).
- **Cerveau** : `/brain`, `/backtest`.
- **Réel (consultation)** : `/accum`, `/accum_reel`, `/futures`, `/revue`, `/portefeuille` (`/wallet`).
- **Assistant IA** : `/ask`, `/forget`.
- **Pipeline paper (simulation)** : `/signals`, `/preorders`, `/approve_preorder`, `/approval_journal`, `/dry_run_order`, `/execution_journal`, `/paper_positions`, `/paper_journal`, `/guard_journal`.
- **Contrôle boucle** : `/run_once` (**désactivé** §45), `/pause`, `/resume`, `/pause_status`.
- `telegram_notifier.py` pousse un résumé toutes les 15 min (bandeau PAPER/DRY_RUN, compact_report, order_signals, pré-ordres, paper_report).

### Famille 3 — Dashboard web (`dashboard/server.py`, 127.0.0.1:8787)
Stdlib Python (`http.server`), jamais exposé Internet (tunnel SSH ou nginx+auth+HTTPS). Endpoints `/`, `/api/state`, `/healthz`, `/vendor/*.js`. ~30 panneaux : Wallet/Performance, Model Confidence, Chart+Order Book, Order-flow, Positions, **Cerveau/Essaim** (biais, conviction, consensus, cognition, votes par agent), Accumulation/Mandat/Échelle d'edge, Consensus univers, **Futures RÉEL/Boucle auto**, Microstructure live, Market-timing, Caps, Système/fleet, Audit IC live, Futur/Éventail, Probability Lattice, Palette du savant, Relationship Graph, On-chain BTC/Stablecoins, Vol implicite/Carry, Macro/Régime, Sentiment, Liquidations, Journal de bord, Prochains rendez-vous, Labo xs paper.

### Famille 4 — Assistant LLM (`assistant/`)
Assistant conversationnel crypto **lecture seule** (Telegram `/ask` + vision de charts). `agent.py` (boucle agentique 6 itérations, durci `prompt_guard`), `llm_client.py` (multi-fournisseur : Anthropic par défaut, ou endpoint OpenAI-compatible Groq/Gemini/Ollama), `tools.py` (**22 outils read-only** : order_flow, technicals, macro, confluence, token_safety, defi, news, prices, aggregated_derivs, prediction_markets, brain_read, liquidations, calendar, arbitrage, tradfi, cross_exchange, backtest…), `vision.py` (analyse d'images de charts, Gemini, texte traité comme hostile), `memory.py` (mémoire de conversation, `/forget`).

### Famille 5 — Infra systemd (cadences §63)

| Unité | Cadence | Lance | Rôle |
|---|---|---|---|
| `bitget-brain` | **1 min** (cycle ~18 s) | `brain_cycle.py` | 14 agents votent + apprennent (bloqué si KILL_SWITCH) |
| `bitget-scan` | **1 min** | `scan_paper.py` | Scan paper (bloqué si KILL_SWITCH) |
| `bitget-watchdog` | **5 min** | `watchdog.py --alert` | Alerte DOWN/STALE (carte fraîcheur) |
| `bitget-notify` | **15 min** | `telegram_notifier.py` | Résumé Telegram (silencieux si KILL_SWITCH) |
| `bitget-validation` | **6 h** | `brain_validation.py` | Validation T5 (replay + porte profonde) |
| `bitget-spend-watch` | **horaire** | `accum_spend_watch.py` | Tripwire dépense + stop futures (arme kill-switch) |
| `bitget-mtiming` | **quotidien** | `market_timing_watch.py` | Market-timing macro/sentiment |
| `bitget-micro-watch` | **hebdo** | `microstructure_watch.py` | Edge microstructure |
| `bitget-logrotate` | **03:30 UTC** | `rotate_logs.sh` | Rotation gzip des journaux |
| `bitget-backup` | **03:40 UTC** | `backup_registres.py` | Sauvegarde chiffrée → Telegram |
| `bitget-security-audit` | **04:00 UTC** | `security_agent.py` | Audit sécurité quotidien |
| `bitget-revue` | **dim. 18:00 UTC** | `revue_hebdo.py --send` | Revue hebdo → Telegram |
| `bitget-bot` / `bitget-dashboard` / `bitget-microstructure` | daemons | — | Bot Telegram / dashboard / collecteur WS L2 |

### Famille 6 — Scripts ops (racine, SAFE)
`update_vps.sh` (pull → deps → GATE tests+sécurité → restart des services **si `VERDICT: SAFE`**), `setup_vps.sh`, `bootstrap_termux.sh`, `restart_agent.sh`, `rotate_logs.sh`, `gates.sh` (3 portes), `cache_warmer.py` (pré-chauffe le runtime_cache).

---

## 9 — OUTILS MANQUANTS

### ROADMAP.md — items non cochés
- Priorité 4 : **« Journal des signaux ignorés »**, **« Gestion des signaux ambigus »**.
- Feuille cerveau (§45) : **régression logistique / gradient boosting** sur bonnes features (« si plus d'apprentissage ») ; **enrichissement différé MCP CoinDesk / Bigdata derrière le cache + TDLib (Telegram)**.

### docs/EXTERNAL_TOOLS.md — « prochaines adoptions » prévues, non intégrées
- **prediction-mcp (Polymarket)** côté PC — Kalshi est branché (§59), le volet Polymarket reste à câbler côté exécution.
- **Module CVD / order-flow + zones de liquidation** dédié (depuis OI/funding/carnet Bitget).
- **Squelette de skill « analyse »** (disclaimer + permissions par outil).
- **CFTC COT** hebdo comme couche de positionnement.

### Sources de données prévues mais NON câblées (nom de variable seulement)
- **Social** (le maillon le plus faible : seuls Fear & Greed + CryptoPanic sont câblés) : X/Twitter, Reddit, Neynar/Farcaster, LunarCrush.
- **Solana** : Birdeye, Helius, RPC Solana, Jupiter.
- **Divers** : FMP, Finnhub ; clé FRED JSON inexploitée (FRED tourne en CSV) ; CoinPaprika/GeckoTerminal documentés keyless mais sans connecteur.
- **Canal `onchain_btc` dormant** (orthogonal, gelé §62) ; **sous-système news quasi clos** (CryptoPanic payant refusé §60).

### Agents manquants
**AUCUN.** Les 20 fichiers déclarés dans `agents_manifest.py` existent tous (`missing_agents()` = 0).

### Lacunes d'observabilité / risque (prioritaires — révélées par l'incident du jour)
- **Enforceur du stop −5 % indépendant de la boucle cerveau/scan** : aujourd'hui le stop immédiat est mort avec la boucle (2 h de délai avant kill-switch).
- **Supervision / redémarrage automatique fiable** des services brain+scan, distinct de la microstructure (le cerveau a re-gelé ~2 h malgré les verrous §61).
- **Volume insuffisant pour trancher** : `exit_lab` < 10 fermetures réelles, verdict directionnel < 30 fills → conventions SL 1,5·ATR / RR 2 non validées sur données réelles.

### TODO/FIXME dans le code
Quasi inexistants — 2 occurrences seulement, dans des docstrings décrivant des bugs **déjà corrigés**.

---

## 10 — SOURCES DE DONNÉES

**26 sources externes réellement câblées** (21 sans clé + 5 à clé). Aucune valeur de secret lue ; noms de variables `.env` uniquement.

### A. Sans clé — RÉELLEMENT câblées

| Fournisseur / API | Catégorie | Donnée | Module(s) |
|---|---|---|---|
| **Bitget REST public** | marché + dérivés | OHLCV, history-candles, carnet L2, tape fills, OI, funding, tickers, long/short | `bitget_market_data`, `candles_history`, `funding_history`, `derivs_positioning`, `aggregated_derivs`, `universe`, `microstructure`, `order_flow` |
| **Bitget WebSocket public** | marché | carnet L2 `books15` + tape temps réel | `book_collector` |
| **CoinGecko** (clé démo optionnelle) | marché | prix, market cap, dominance, OHLC de repli, top market-cap | `coingecko_data`, `market_sources`, `universe` |
| **Binance / Bybit / OKX public** | dérivés + marché | funding, open interest, prix spot | `derivs_positioning`, `aggregated_derivs`, `arbitrage` |
| **CCXT** (optionnel) | marché + dérivés | prix, funding, OI multi-exchange | `ccxt_markets` |
| **Deribit** | dérivés (vol) | indice DVOL + vol réalisée → VRP | `deribit_vol` |
| **DefiLlama (chains + stablecoins)** | on-chain | TVL DeFi + offre de stablecoins → dry powder | `defi_data`, `stablecoin_flow` |
| **DexScreener** | on-chain / DEX | paires par liquidité, volume, âge | `dex_scanner` |
| **GoPlus / Honeypot.is / RugCheck** | on-chain | sécurité token EVM + rug report Solana | `token_safety` |
| **blockchain.info / mempool.space** | on-chain | hashrate BTC + frais/difficulté | `onchain_btc` |
| **FRED (CSV keyless)** | macro | VIX, 2s10s, DXY, WTI, NFCI, HY OAS, FEDFUNDS, DGS10/2 | `macro_context`, `macro_sentinel`, `macro_data` |
| **RSS Fed + BCE** | macro | titres banques centrales (assainis) | `macro_sentinel` |
| **Forex Factory** | macro | calendrier éco (FOMC/CPI/NFP/PCE) | `econ_calendar` |
| **alternative.me** | sentiment | Fear & Greed Index | `sentiment_index` |
| **Polymarket (Gamma API)** | prédiction | probabilités implicites | `polymarket_data` |

### B. À clé gratuite — RÉELLEMENT câblées

| Fournisseur | Catégorie | Donnée | Variable `.env` | Module |
|---|---|---|---|---|
| **CryptoPanic** | news | news crypto + sentiment | `CRYPTOPANIC_API_TOKEN` | `news_feed` |
| **AlphaVantage** | macro (TradFi) | proxys ETF SPY/UUP/GLD | `ALPHAVANTAGE_API_KEY` | `macro_data` |
| **TwelveData** | macro (TradFi) | XAU/USD, EUR/USD | `TWELVEDATA_API_KEY` | `macro_data` |
| **Kalshi** | prédiction | échéances macro (Fed, CPI) → black-out | `KALSHI_API_KEY` | `kalshi_probe` → `macro_context` |
| **CoinGecko (clé démo)** | marché | idem A, rate-limit levé | `COINGECKO_API_KEY` | `coingecko_data`, `universe` |

### C. Prévues mais NON câblées (nom de variable seulement)
FMP, Finnhub, Birdeye, Helius, RPC Solana, X/Twitter, Neynar, Reddit, LunarCrush (+ CoinPaprika/GeckoTerminal/Jupiter documentés keyless sans connecteur ; clé FRED JSON inexploitée).

### D. Infrastructure (clés, PAS des sources marché)
- **Bitget privé** (`BITGET_API_KEY/SECRET/PASSPHRASE`, Trade-only) — lecture compte + ordres réels.
- **Telegram** (`TELEGRAM_BOT_TOKEN`, `COMMAND_BOT_TOKEN`, `TELEGRAM_CHAT_ID`).
- **LLM** (`ANTHROPIC_API_KEY` ou `LLM_BASE_URL`/`LLM_API_KEY`/`LLM_MODEL`).
- **Vision** (`VISION_API_KEY`/`VISION_MODEL`/`VISION_BASE_URL`, Gemini).
- **Sauvegarde** (`BACKUP_PASSPHRASE`).

### E. MCP de session (hors runtime bot)
CoinDesk MCP, Bigdata.com, prediction-mcp/Polymarket — disponibles dans la session de build, pas dans le bot lui-même.

### Constat
Cœur marché/dérivés keyless **solide et redondant** ; on-chain complet **sauf Solana** ; macro mixte FRED + TradFi ; **social = maillon faible** ; prédiction OK (Polymarket + Kalshi).

---

## ANNEXE — Projets annexes du VPS

Projets présents sur le même VPS, **indépendants** du bot de trading.

| Projet | Nature | Stack | État | Lien bot Bitget |
|---|---|---|---|---|
| `/opt/Agents_brain-` | Socle générique d'agents IA gestion/compta belge (« Projet Zéro », à cloner) | Docker : FastAPI `brain-api` + LiteLLM + Postgres/Qdrant/MinIO/NATS/Open WebUI | **Actif** (7 services Up ~13 j ; tâches **simulées**, permissions sensibles OFF par défaut) ; produit au stade MVP | Indépendant (même propriétaire ; agent « Crypto Accounting » prévu en lecture seule ; **aucune intégration**) |
| `/root/financial-services` | Clone officiel **anthropics/financial-services** (plugins/cookbooks finance) | Markdown/JSON, plugins Cowork + Managed Agents API, connecteurs MCP | Dépôt de référence à jour, non modifié, ne « tourne » pas | Aucun (matériel de référence) |
| `/docker/n8n` | Automatisation de workflows | n8n + Traefik (HTTPS Let's Encrypt) | **Actif, exposé publiquement** (occupe le port 5678 → bloque le n8n d'Agents_brain-) | Non démontré (workflows dans volume non versionné) |
| `bitget_termux_repo~` | **Ancienne sauvegarde** du bot (paper/dry-run strict) | Python, 60 fichiers | Figé au 20/06/2026, tag `stable-paper-dryrun-20260620`, dépassé (principal = 543 fichiers) | C'est le bot lui-même, dernière image « 100 % paper » avant le live §45 |

**Note d'hygiène** : les docs d'install d'`Agents_brain-` contiennent l'IP publique du VPS en clair (pas un secret au sens strict, mais à ne pas versionner). Aucun `.env` n'a été lu lors de l'audit.

---

*Fin du document. Source : audit exhaustif du VPS (9 lecteurs parallèles + vérifications directes), 2026-07-05.*
