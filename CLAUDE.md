# CLAUDE.md — contexte & règles pour tout agent travaillant sur ce dépôt

Bot de trading Bitget avec un **cerveau déterministe en mixture-of-experts** (11 agents,
pondération adaptative EARCP). **AUCUN réseau de neurones** (contrainte du propriétaire).
Tourne sur un VPS Ubuntu (`~/bitget_termux_repo`). Branche de travail :
`claude/beautiful-heisenberg-c5aoqu`.

## ⚠️ RÈGLES D'ENGAGEMENT (à respecter absolument)

1. **Argent réel en jeu.** Une seule chose touche le réel : l'achat **spot BTC** d'accumulation
   (`spot_executor.py`), plafonné **5 $/jour**, jamais de vente/levier/futures/retrait.
   **Tout le reste est paper / DRY-RUN.**
2. **Ne JAMAIS lever un verrou sans instruction explicite du propriétaire** :
   `MANDATE_LIVE_ENABLED`, `ACCUM_AUTONOMOUS_LIVE`, les plafonds (`ACCUM_REAL_MAX_*`).
   Le futures reste paper tant qu'aucun agent ne franchit la porte d'edge (cf. `edge_ladder`).
3. **Ne jamais passer en mode full-auto** sur cette machine (elle détient les vraies clés).
   Garder les confirmations sur les commandes sensibles.
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
| Accumulation spot BTC | **RÉELLE** : `limit_ioc` anti-slippage, ≤5 $/j, garde best-price, double verrou |
| Cerveau (11 agents), scan, pré-ordres, futures | **PAPER / DRY_RUN_ONLY** (`execution_gateway`) |
| Échelle d'edge | 0 agent LIVE (rien d'éligible au réel) |

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
python accumulation_engine.py BTCUSDT           # état accumulation (mode, opportunité, premium)
python universe.py                              # univers d'analyse courant
```

Commits : messages clairs en français, et **ne jamais inclure d'identifiant de modèle**
dans un commit/PR/artefact. Pousser seulement après les 3 portes vertes.
