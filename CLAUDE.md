# CLAUDE.md — contexte & règles pour tout agent travaillant sur ce dépôt

Bot de trading Bitget avec un **cerveau déterministe en mixture-of-experts** (13 agents,
pondération adaptative EARCP). **AUCUN réseau de neurones** (contrainte du propriétaire).
Tourne sur un VPS Ubuntu (`~/bitget_termux_repo`). Branche de travail :
`claude/beautiful-heisenberg-c5aoqu`.

## ⚠️ RÈGLES D'ENGAGEMENT (révisées le 02/07/2026 — décision propriétaire, §45)

1. **Argent réel en jeu.** Deux modules — et SEULEMENT eux — passent des ordres réels :
   - `spot_executor.py` : achat spot BTC d'accumulation, ≤5 $/j, jamais de vente/retrait ;
   - `futures_executor.py` : futures BORNÉ (§45) — marge ISOLÉE, levier ≤×5, murs en dur
     50 $/trade et 250 $ cumulé (env/config peuvent abaisser, JAMAIS dépasser), stop de
     perte journalier (−5 % -> kill-switch), jamais de retrait/virement/annulation.
   Le cerveau/scan/pré-ordres restent paper tant qu'ils ne passent pas par ces modules.
2. **Ne JAMAIS lever un verrou sans instruction explicite du propriétaire** :
   `MANDATE_LIVE_ENABLED`, `ACCUM_AUTONOMOUS_LIVE`, `FUTURES_AUTONOMOUS_LIVE`,
   les plafonds (`ACCUM_REAL_MAX_*`, `FUTURES_REAL_MAX_*`), `FUTURES_EDGE_GATE_OVERRIDE`.
   §45 (02/07/2026) : le propriétaire a ARMÉ le futures réel et OUTREPASSÉ la porte
   d'edge en connaissance de cause (0 agent LIVE, espérance directionnelle mesurée
   négative — trois questions d'engagement répondues). `FUTURES_EDGE_GATE_OVERRIDE=0`
   referme la porte instantanément.
3. **Full-auto autorisé DANS les murs (§45)** — mais la montée des caps effectifs reste
   une décision propriétaire explicite, par paliers, si l'exécution est propre.
   Kill-switch d'urgence : `touch KILL_SWITCH` (bloque spot ET futures).
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
6. **Classer chaque module SAFE** (lecture seule / paper) — un fichier qui passe un ordre
   réel doit être `spot_executor.py` (achat spot BTC seul, avec ses gardes).

## État réel vs paper

| Composant | État |
|---|---|
| Lecture compte (portefeuille complet) | RÉEL, lecture seule (`bitget_hub_bridge`, `bitget_balance_reader`) |
| Accumulation spot BTC | **RÉELLE** : `limit_ioc` anti-slippage, 2–5 $/j ∝ opportunité (§44), garde best-price, double verrou |
| Futures borné (`futures_executor`) | **RÉEL depuis §45** : marge isolée, ≤×5, caps 15/60 (murs 50/250), stop journalier −5 % -> kill-switch |
| Cerveau (13 agents), scan, pré-ordres | **PAPER** (`execution_gateway` DRY_RUN_ONLY — le câblage cerveau->futures réel est un chantier §45 séparé) |
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
- Détails & historique des décisions : `docs/RESEARCH_NOTES.md` (§1–33).

## Leviers `.env` (jamais committés)

```
DYNAMIC_UNIVERSE=1          # univers dynamique top-N
ACCUM_AUTONOMOUS_LIVE=1     # accumulation auto réelle (sinon manuelle)
EXEC_STYLE=limit_ioc        # défaut ; "taker" = marché ; "maker" = post-only
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

Commits : messages clairs en français, et **ne jamais inclure d'identifiant de modèle**
dans un commit/PR/artefact. Pousser seulement après les 3 portes vertes.
