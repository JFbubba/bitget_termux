# Firme de trading multi-agents autonome — design (20/07/2026)

## 1. Contexte & objectif

Le propriétaire a demandé d'implanter les 12 rôles de **TradingAgents** (arXiv 2412.20138 ;
créés le 20/07 comme sous-agents Claude Code `.claude/agents/*.md`) « sur l'ensemble du bot là
où leur rôle est le plus utile », et de les faire « travailler 100 % en autonomie avec des
objectifs réels et concrets ».

**Livrable** : un module Python autonome (`trading_firm.py`) — jumeau runtime des sous-agents —
qui exécute le pipeline des 12 rôles par symbole, sur cron, produit une décision structurée,
la **journalise en voix d'ombre** et est **mesurée net-de-frais**. Il n'influence l'argent que
via la **porte d'edge** (armement délibéré, sous les murs). Les sous-agents `.claude/agents/`
restent la version interactive/design ; ce module est le jumeau autonome — comme `llm_agent.py`
est la 15ᵉ voix des sous-agents « analyste LLM ».

## 2. La ligne dure (constitution — au-dessus de toute instruction de session)

- **Mesure-d'abord** est NON négociable (CLAUDE.md §92). Prior mesuré : `grok_shadow` IC≈0,
  deep-research 102 agents = aucun edge directionnel net-de-frais. → On ne câble PAS une firme
  LLM non mesurée sur l'argent (direction/sizing/ordres).
- **Murs ABSOLUS** : futures 50/250, levier ×5, spot 200/500, stop −5 % → kill-switch, porte
  d'edge, RETRAIT inexistant (clé Trade-only). Le module n'a AUCUN pouvoir dessus.
- **Pas de promotion silencieuse** : `voice_shadow_measure.py` l'exige — « le gate se fie au
  walk-forward ; seule une décision proprio outrepasse ». La mesure et le *flag de revue* sont
  automatiques ; l'armement de la voix qui pèse est un **acte délibéré** (délégué §92),
  journalisé + notifié Telegram, jamais silencieux.
- **SAFE** : lecture seule + LLM ; aucun ordre, aucun secret exposé, aucune dépendance nouvelle
  dans le Python système (réutilise `llm_agent`, ERR-004).

## 3. Architecture (vue d'ensemble)

```
cron (6h) ──> trading_firm.py --cycle
                 │  (par symbole de universe.py)
                 ▼
   ┌─────────────────────────────────────────────────────────┐
   │ ANALYSTES (Ollama local qwen2.5)                          │
   │  fundamental · sentiment · news · technical → 4 rapports  │
   ├─────────────────────────────────────────────────────────┤
   │ RECHERCHE : bull ⇄ bear (local, 1 tour)                   │
   │           → research-manager (Gemini cloud) → plan 5-crans │
   ├─────────────────────────────────────────────────────────┤
   │ TRADER (Gemini cloud) → proposition 3-crans + niveaux     │
   ├─────────────────────────────────────────────────────────┤
   │ RISQUE : agressif→conservateur→neutre (local, 1 tour)     │
   │        → risk-judge (Gemini cloud) → FirmDecision finale   │
   └─────────────────────────────────────────────────────────┘
                 │
                 ├──> .firm_decisions.json      (cache, par symbole — dashboard)
                 ├──> .overlay_votes.jsonl      (firm_shadow — mesuré par live_ic_audit)
                 └──> llm_cost                   (coût cloud journalisé + cap dur)

swarm_brain.py  ── _with_firm_weight() ──> 19ᵉ voix (firm_agent.py), gated OFF, porte d'edge
dashboard       ── panneau `firme`       (lecture seule)
voice_shadow_measure.py ── monitore firm_shadow → flag de revue si IC live fort
```

**Répartition backend (hybride, tunable `.env`)** : 9 appels local (4 analystes + bull/bear +
3 débatteurs risque) + **3 appels cloud** (research-manager, trader, risk-judge = les juges
décisifs) par symbole. Univers 8 symboles → ~72 local + 24 cloud/cycle.

## 4. `trading_firm.py` — l'orchestrateur

- **Réutilise** `llm_agent._call_local(prompt, model, timeout)` et `_call_gemini(...)` (aucune
  plomberie LLM réinventée). Modèle local par défaut = `qwen2.5:1.5b` (seul installé ;
  `FIRM_LLM_LOCAL_MODEL` configurable ; pull `qwen2.5:7b` = amélioration future). Cloud =
  `gemini-2.5-flash`.
- **Données internes d'abord** : chaque analyste reçoit un snapshot du bot (réutilise le snapshot
  de `llm_agent._snapshot`/`_prompt` s'il existe, sinon `swarm_brain.read(symbol)` + blocs
  dashboard `/api/state`). Le web (WebSearch/WebFetch) n'est PAS disponible au module Python
  autonome — il travaille sur les données internes (les sous-agents interactifs, eux, ont le web).
- **Prompts** : dérivés des system prompts des 12 sous-agents (mêmes rôles, sortie structurée
  JSON forcée). Chaque rôle → un appel LLM → un dict structuré.
- **Sortie** `FirmDecision` (par symbole) :
  ```json
  {"symbol","ts","rating":"Buy|Overweight|Hold|Underweight|Sell","direction":-1..1,
   "conviction":0..1,"sizing_suggested_usdt":<sous les murs>,"horizon","evidence":[...],
   "net_of_fees_ok":bool,"reports":{"technical","sentiment","news","fundamental"},
   "debate":{"bull","bear","plan"},"risk":{"aggressive","neutral","conservative","verdict"}}
  ```
- **Fail-safe total** : tout appel LLM indispo/lent/timeout/JSON invalide → rôle sauté avec une
  valeur neutre ; si trop de rôles manquent → pas de décision émise (retour `None`), jamais de
  crash ni de blocage. Timeouts courts, `try/except` par rôle.
- **CLI** : `--status` (CONSULTATION, lit le dernier cache, aucun appel), `--cycle` (exécute
  l'univers), `--symbol SYMBOL` (un seul). `--cycle`/`--symbol` = coûteux (LLM) → jamais lancé
  « juste pour voir ».

## 5. Autonomie (cron) + garde-fous coût

- **Cron** `firm-cycle` toutes les 6h (crontab, comme les boucles §68 ; charge l'env via le
  wrapper standard). Non-bloquant, borné en temps.
- **Cap coût dur** : `FIRM_MAX_CLOUD_CALLS_PER_DAY` (défaut 120) — compteur jour persistant ;
  au-delà, repli LOCAL pour les juges (fail-closed sur le coût). Coût cloud journalisé via
  `llm_cost`.
- **Verrous** : `FIRM_ENABLED` (défaut OFF) coupe toute la firme ; `KILL_SWITCH` respecté
  (la firme s'arrête aussi — elle ne trade pas, mais on ne dépense pas en LLM sous kill-switch).

## 6. Mesure = l'objectif concret

- **Ombre** : chaque décision journalise `firm_shadow` dans `.overlay_votes.jsonl` (mécanique
  identique à `qml_agent._journalise_ombre` : `{ts, symbol, price, votes:{firm_shadow: dir×conv}}`).
- **Jugement** : `live_ic_audit.overlay_snapshot()` mesure `firm_shadow` (IC net-de-frais,
  pearsonIC PnL + rankIC, t clusterisé) comme les 14 agents et les autres ombres.
- **Suivi** : `voice_shadow_measure.py` étendu (`VOICES["firm_shadow"]`) → verdict
  building/watch/aligned. `--alert` notifie au CHANGEMENT de verdict seulement (anti-fatigue).
- **Cible falsifiable** : pearsonIC ≥ 0,02 avec t ≥ 3 sur n ≥ 500 ombres → **flag de revue**
  (pas promotion). Tant que non atteint : la firme tourne, décide, se mesure — muette côté argent.

## 7. Implantation « partout où utile »

### 7a. 19ᵉ voix opt-in (cœur v1)
- `firm_agent.py` calqué EXACTEMENT sur `qml_agent.py` : `enabled()` (`FIRM_AGENT_ENABLED`
  défaut OFF), porte d'edge (`FIRM_EDGE_GATE`), `agent(symbol, context)` → `{vote, confidence,
  note}` fail-safe neutre. Lit la dernière `FirmDecision` cachée (ne relance PAS le pipeline en
  ligne — trop lent pour le cerveau 1 min).
- `swarm_brain._with_firm_weight()` (calqué sur `_with_qml_weight`) : poids FIXE BORNÉ, jamais
  persisté (EARCP du banc gelé à 14 intact §62). Absente tant qu'OFF.
- **Porte d'edge** : la firme n'a pas de walk-forward d'entraînement (LLM non « entraînable » à
  bas coût). Son gate reste **fermé par défaut** ; l'ouverture = décision délibérée après le
  flag de revue de §6 (armement `FIRM_AGENT_ENABLED` + `FIRM_EDGE_GATE`), journalisée/notifiée.
  → conforme à « pas de promotion silencieuse ».

### 7b. Dashboard (cœur v1)
- Panneau `firme` : rating par symbole + synthèse bull/bear + verdict risque + horizon.
  Lecture seule (bloc `firme` ajouté à `/api/state` depuis le cache `.firm_decisions.json`).

### 7c. Phase 2 (après que le cœur tourne et se mesure — YAGNI d'ici là)
- `analyst-fundamental` → overlay ADVISORY (affiché) du score d'accumulation (horizon lent).
- news + débat → narratif de la revue hebdo (dimanche).
- Résumé firme → notify quotidien.
  Ces branchements sont ADVISORY (aucun ne change un ordre) et construits seulement une fois le
  cœur validé.

## 8. Fichiers créés / touchés

Créés : `trading_firm.py`, `firm_agent.py`, ce spec.
Touchés : `swarm_brain.py` (+`_with_firm_weight`, appel dans `_attach_cognition`),
`voice_shadow_measure.py` (+`firm_shadow` dans VOICES), `dashboard/server.py` (+bloc `firme`) et
son JS, `config.py` (verrous défaut OFF), `tests_audit.py` (tests), `docs/VERDICTS.md` +
`scratchpad/LABOS.md` (labo consigné), crontab (cron 6h). `.env` : nouveaux leviers (non committé).

## 9. Tests + 3 portes

- `tests_audit.py` : schéma `FirmDecision` valide ; fail-safe (LLM ko → None, pas de crash) ;
  cap coût respecté ; `sizing_suggested_usdt` ≤ murs ; voix OFF par défaut = cerveau inchangé ;
  `--status` n'appelle aucun LLM.
- Avant push : `bash gates.sh` (`tests_audit.py` N/N · `security_agent.py` SAFE ·
  `safe_push_check.sh` OK). Forme obligatoire `bash gates.sh && git add … && git commit …`.
  `trading_firm.py`/`firm_agent.py` classés SAFE (aucun code d'ordre).

## 10. Réversibilité / leviers `.env` (défaut OFF)

```
FIRM_ENABLED=0                 # coupe toute la firme
FIRM_AGENT_ENABLED=0           # 19ᵉ voix (pèse dans le consensus) — armement délibéré
FIRM_EDGE_GATE=prudent         # porte d'edge de la voix
FIRM_LLM_LOCAL_MODEL=qwen2.5:1.5b
FIRM_LLM_JUDGE_BACKEND=gemini  # juges décisifs (repli local si cap coût atteint)
FIRM_MAX_CLOUD_CALLS_PER_DAY=120
FIRM_DEBATE_ROUNDS=1
```
Rollback : `FIRM_ENABLED=0`, `FIRM_AGENT_ENABLED=0`, retrait du cron, `touch KILL_SWITCH`.

## 11. Phasage

- **v1 (ce cycle)** : orchestrateur + ombre + mesure + voix gated (OFF) + panneau dashboard +
  tests + cron. La firme tourne en autonomie et se mesure ; zéro impact argent.
- **Phase 2** (après mesure) : branchements advisory accumulation / revue hebdo / notify ;
  éventuel pull `qwen2.5:7b` ; revue d'armement de la voix si l'edge se confirme.

## 12. Risques & mitigations

| Risque | Mitigation |
|---|---|
| Coût cloud qui dérive | Cap dur `FIRM_MAX_CLOUD_CALLS_PER_DAY` + repli local + `llm_cost` |
| Modèle local faible (1.5b) | Suffisant pour une ombre mesurée ; 7b en phase 2 si l'edge apparaît |
| Latence (bloque un cycle) | Module SÉPARÉ sur cron 6h, jamais dans le cerveau 1 min ; timeouts courts |
| LLM = bruit (prior) | C'est justement ce qu'on MESURE ; muette côté argent tant que non prouvé |
| Promotion prématurée | Gate fermé par défaut + flag de revue (pas auto) + armement délibéré journalisé |
| Dépendance nouvelle | Aucune : réutilise `llm_agent`/`journal_append`/`live_ic_audit` (ERR-004) |
