# Carte mentale et organisationnelle — bitget_termux

## Synthèse

`bitget_termux` est un agent local Termux Android pour monitoring Bitget Futures en mode paper / dry-run. Le dépôt est conçu pour analyser, journaliser, notifier et simuler des signaux sans envoyer d'ordre réel.

## Carte mentale

```mermaid
mindmap
  root((bitget_termux))
    Sécurité
      can_trade_false
      dry_run_only
      security_agent
      tests_audit
      safe_push_check
      interdiction_ordres_reels
    Orchestration
      agent_loop
      agent_control
      agent_hub
      watchdog
      restart_agent
    Données_marche
      config
      universe
      bitget_market_data
      indicators
      pro_indicators
      order_flow
      macro_context
      news_feed
    Analyse_signaux
      journal_scanner
      brain_cycle
      brain_validation
      technicals
      geometric_agent
      macro_regime
    Simulation_trading
      order_signal_engine
      preorder_engine
      preorder_guard
      preorder_approval
      execution_gateway
      paper_positions
      paper_position_reconciler
      outcome_state
    Risque_reporting
      risk_manager
      risk_limits
      compact_report
      state_report
      stats_report
      account_equity
      edge_ladder
    Interfaces
      telegram_command_bot
      telegram_notifier
      dashboard_server
      bitget_hub_bridge
      assistant_llm_client
    Exploitation
      bootstrap_termux
      rotate_logs
      git_version
      system_health
      update_vps
```

## Organisation fonctionnelle

```mermaid
flowchart TD
  A[agent_loop.py] --> B[agent_control.py]
  B --> C[outcome_state.py]
  B --> D[universe.py]
  B --> E[brain_cycle.py]
  B --> F[journal_scanner.py]
  B --> G[paper_position_reconciler.py]
  B --> H[state_report.py]
  B --> I[compact_report.py]
  B --> J[order_signal_engine.py]
  B --> K[preorder_engine.py]
  B --> L[preorder_guard.py]
  B --> M[telegram_notifier.py]
  B --> N[brain_validation.py]
  B --> O[mandate.py]
  B --> P[edge_ladder.py]
  B --> Q[bitget_hub_bridge.py]
  B --> R[accumulation_engine.py]

  F --> S[signals_journal.csv]
  C --> T[open_outcomes_state.csv]
  C --> U[final_outcomes_journal.csv]
  K --> V[pending_orders]
  G --> W[paper_positions]

  X[config.py] --> B
  Y[security_agent.py] --> Z[agents_manifest.py]
  AA[tests_audit.py] --> Y
```

## Couches du repo

### 1. Couche sécurité

Rôle : empêcher que le système devienne un bot de trading réel non contrôlé.

Fichiers principaux :

- `security_agent.py`
- `agents_manifest.py`
- `tests_audit.py`
- `safe_push_check.sh`
- `config_guard_agent.py`

Règle : les agents du manifeste sont `can_trade=False`.

### 2. Couche orchestration

Rôle : lancer les cycles, enchaîner les modules et surveiller l'exécution.

Fichiers principaux :

- `agent_loop.py`
- `agent_control.py`
- `agent_hub.py`
- `watchdog.py`
- `restart_agent.sh`

### 3. Couche données et indicateurs

Rôle : préparer l'univers, les bougies, l'order flow, les indicateurs et le contexte macro.

Fichiers principaux :

- `config.py`
- `universe.py`
- `bitget_market_data.py`
- `indicators.py`
- `pro_indicators.py`
- `order_flow.py`
- `macro_context.py`
- `macro_regime.py`
- `news_feed.py`

### 4. Couche analyse et décision paper

Rôle : transformer les données en signaux simulés.

Fichiers principaux :

- `journal_scanner.py`
- `brain_cycle.py`
- `brain_validation.py`
- `technicals.py`
- `geometric_agent.py`
- `order_signal_engine.py`

### 5. Couche pré-ordre et simulation

Rôle : transformer les signaux en pré-ordres puis en simulation paper, sans exécution réelle.

Fichiers principaux :

- `preorder_engine.py`
- `preorder_guard.py`
- `preorder_approval.py`
- `execution_gateway.py`
- `paper_positions.py`
- `paper_position_reconciler.py`
- `outcome_state.py`

### 6. Couche risque et reporting

Rôle : contrôler exposition, performance, états ouverts, résultats et rapports.

Fichiers principaux :

- `risk_manager.py`
- `risk_limits.py`
- `compact_report.py`
- `state_report.py`
- `stats_report.py`
- `account_equity.py`
- `edge_ladder.py`

### 7. Couche interfaces

Rôle : envoyer des notifications, recevoir commandes lecture seule, afficher dashboard et pont Agent Hub.

Fichiers principaux :

- `telegram_command_bot.py`
- `telegram_notifier.py`
- `dashboard/server.py`
- `bitget_hub_bridge.py`
- `assistant/llm_client.py`

## Lecture du flux principal

1. `agent_loop.py` lance un cycle régulier.
2. `agent_control.py` exécute les modules dans l'ordre.
3. Les modules de marché et cerveau produisent des signaux.
4. Les signaux sont transformés en pré-ordres simulés.
5. Les gardes-fous paper vérifient le risque.
6. Le système met à jour les positions paper et résultats.
7. Les rapports et notifications sont générés.
8. Le watchdog vérifie la fraîcheur et la présence de la boucle.

## Points de vigilance

- Le README affirme un mode paper / dry-run only.
- Le manifeste impose `can_trade=False`.
- Certaines variables de `config.py` évoquent des verrous live et accumulation réelle. Ces éléments doivent rester isolés, testés et bloqués par défaut avant toute utilisation sérieuse.
- Les fichiers runtime CSV, JSONL, journaux et secrets ne doivent pas être versionnés.
- Toute connexion exchange doit être en lecture seule au départ.

## Prochaine action recommandée

Avant toute évolution :

```bash
python tests_audit.py
python security_agent.py
python system_health.py
```

Si ces trois commandes ne retournent pas un état sûr, ne pas lancer de boucle longue et ne pas connecter de clé API.
