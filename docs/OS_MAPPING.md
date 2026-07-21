# OS_MAPPING — application du méga-prompt de refonte « OS » (21/07/2026)

Décision propriétaire : le méga-prompt « OS » (plateforme de recherche quant complète)
s'applique **SANS doublon ni suppression de l'existant**. Cette carte est l'application :
chaque chapitre du prompt est mappé sur le module existant qui le porte déjà (le
construire à nouveau serait un doublon), sur ce qui a été construit en delta, sur ce qui
est planifié (backlog), ou sur ce qui est écarté avec motif constitutionnel. Le bot EST
la plateforme — l'application du prompt est additive, jamais une réécriture.

| Chapitre « OS » | Statut | Porté par |
|---|---|---|
| §3.1 Intégrité scientifique (pas de look-ahead, DSR, origine des résultats) | EXISTANT+ | `audit_core` (HAC/DSR), ERR-001/014/016-017, étiquette d'origine (doctrine module-builder 21/07) |
| §3.2 Séparation des responsabilités (LLM jamais sur l'argent) | EXISTANT | Constitution CLAUDE.md (LLM = surcouche opt-in, `guards()` déterministes absolus) |
| §3.3 Mode sécurisé par défaut | EXISTANT | Verrous défaut OFF, DRY, kill-switch fail-closed, clé Trade-only |
| §4 Stack FastAPI/Polars/DuckDB/React/Vite | ÉCARTÉ | Contraire à la réalité VPS (2 cœurs) et à l'existant sain : artefacts JSON + dashboard JS vanilla lecture seule. Une migration = doublon massif sans mesure de gain |
| §6 Couche de données + DATA HEALTH | EXISTANT+ | `candles_history`/`funding_history` (6 ans/90 j), `data_guards`, carte de fraîcheur watchdog §61 (panneau santé) ; gates qualité-donnée versés dans integration-architect (21/07) |
| §7.1 Moteur vectorisé | EXISTANT | `audit_core` + `agent_validation.replay` (numpy, walk-forward purgé) |
| §7.2 Moteur événementiel (fills/latence/frais) | EXISTANT | `exit_calibration`, `smc_execution_lab`, mesure IOC §109 sur fills RÉELS (mieux qu'une simulation) |
| §7 Tests de parité entre moteurs | CONSTRUIT 21/07 | `parity_harness.py` — capture live → rejeu sans réseau → comparaison exacte, multi-paires (`--univers`), cron 07:10 |
| §8 Bibliothèque de stratégies + contrôle négatif | EXISTANT+ | `classics_agent` (10 familles §72), strategy-lab dim 05:00 ; contrôle négatif = doctrine module-builder (21/07) |
| §9 Strategy Arena (arms, machine d'états, leaderboard multi-objectifs) | EXISTANT | `edge_ladder` (états T5), `live_ic_audit` (IC live/voix), `promotion_board`, revue hebdo §60 — jamais un classement au PnL seul (DSR/stabilité) |
| §10 Validation (CPCV, embargo, PBO, DSR, Reality Check) | CONSTRUIT 21/07 (diagnostic) | DSR/PSR/purge EXISTANTS ; **CPCV multi-chemins porté dans `agent_validation`** (diagnostic journalisé, non-gating — l'armer en porte = commit isolé, hygiène d'armement) |
| §10 Registre d'usage du holdout (untouched/contaminated) | CONSTRUIT 21/07 | Registre des consultations du replay profond (journal JSON, statut par version) |
| §11 Optimisation (Optuna, TPE, grilles) | ÉCARTÉ | Mesure-d'abord : la sur-recherche de paramètres EST le risque (DSR pénalise les essais) ; pénalisation de complexité déjà dans la doctrine ; pas de grille massive |
| §12 Allocation adaptative (bandits, vol-parity) | EXISTANT | EARCP §51 (poids adaptatifs bornés), Kelly §111 (calculateur de mise ÷ budget corrélé), vol-targeting GARCH (`mandate`) |
| §13 Self-healing gouverné (échantillon min, proposer≠imposer) | EXISTANT | Revue hebdo §60 (recommandations chiffrées), boucles §68, hygiène d'armement, vetos adversarial-reviewer (trade isolé ≠ signal) |
| §14 Multi-agents JSON + socle commun | APPLIQUÉ 21/07 | 13 des 24 prompts `.claude/agents/` enrichis des deltas réels (ABSTAIN, origine des preuves, martingale=REJECT…) |
| §15 RiskGovernor indépendant | EXISTANT | `guards()`/`risk_manager` + `stop_guardian` (process indépendant 20 s, flatten) + tripwires + black-out macro §59 |
| §16 BrokerAdapter (idempotence, réconciliation, reprise) | EXISTANT | SAVOIR §11 (invariants), §109 accepté≠rempli, `accum_reconcile`, BITGET_REFERENCE §10 |
| §17 Terminal/cockpit | EXISTANT | Dashboard lecture seule (SWR, gzip, bandeau stale, Kelly §111, jamais de chiffre fictif — doctrine 21/07) |
| §18 Performance (mesurer avant d'optimiser) | EXISTANT | Doctrine perf-auditor + mesures réelles (SWR 9,9 s → 0,05 s ; chemin froid §111) |
| §19 Observabilité | EXISTANT | Watchdog §61 (10 artefacts), `system_health`, heartbeats per-cycle (ERR-012), journaux JSONL bornés |
| §20 Sécurité | EXISTANT+ | 3 portes, `security_agent`, sast local, clé Trade-only ; posture clé API versée dans security-auditor (21/07) |
| §21 Tests + chaos | EXISTANT | `tests_audit.py` (700+), tests de kill-switch/fail-closed/ERR-019 ; scénarios de chaos ciblés ajoutés au fil des incidents |
| §22 Rapports traçables (commit/dataset/seed) | EXISTANT+ | Journaux + sessions de parité (commit inclus) ; étiquette d'origine (doctrine 21/07) |
| §23-24 Commandes + démo sans clé | EXISTANT | CLIs `--status` lecture seule, `update_vps.sh`, `gates.sh` ; tests hors-ligne synthétiques |
| §25 Protocole par phases | APPLIQUÉ | Ce mapping = l'audit anti-doublon ; les deltas construits sont listés ci-dessus |
| Scénarios de coûts (perturbation frais/slippage/funding) | CONSTRUIT 21/07 | `lab_scenarios.py` — optimiste/maker/neutre/pessimiste/stress_crise + funding de portage + SEEDS_ROBUSTESSE ; PROMOTION seulement si le net PESSIMISTE survit |

Règle de maintenance : toute reprise future du prompt « OS » (ou d'un bundle similaire)
se triage CONTRE cette carte — on n'installe que ce qui n'y est pas déjà.
