# Roadmap  Bitget Termux Agent

## Phase actuelle

Paper / dry-run only.

Objectif : fiabiliser le moteur local, Telegram, les journaux, les tests et les garde-fous.

## Priorite 1  Securite

- Maintenir tous les agents avec can_trade=False
- Bloquer tout ajout de fonction de trading reel
- Garder .env hors Git
- Ajouter safe_push_check.sh
- Ajouter verification avant push
- Tester security_agent.py avant chaque commit

## Priorite 2  Exploitation Termux

- [x] Ajouter bootstrap_termux.sh
- [x] Ajouter rotation des journaux (rotate_logs.sh)
- [x] Ajouter commande Telegram /git_version
- [x] Ajouter verification de processus agent_loop.py (watchdog.py + /watchdog)
- [x] Ajouter procedure restart propre (restart_agent.sh + agent_loop.pid)

## Priorite 3  Observabilite

- [x] Resume sante systeme (/system_health)
- [x] Dernier commit Git (/git_version)
- [x] Dernier tag stable (/git_version)
- [x] Taille des journaux (/system_health)
- [x] Nombre de pre-ordres pending/rejected/dry-run (/system_health)
- [x] Statut pause/resume (/pause_status)

## Priorite 4  Qualite strategie

- Backtest offline simple
- Journal des signaux ignores
- [x] Indicateurs volume : niveau ancre + biais (concept Unbiased Level Pro)
- [x] Statistiques par symbole (stats_report.py + /stats)
- [x] Statistiques long/short (stats_report.py + /stats)
- [x] Ratio TP/SL (stats_report.py + /stats)
- Gestion des signaux ambigus

## Outils externes

Revue curee des sources externes (data, MCP, skills, Polymarket) et plan
d'adoption SAFE : voir [docs/EXTERNAL_TOOLS.md](docs/EXTERNAL_TOOLS.md).
Prochaines adoptions : prediction-mcp (Polymarket, cote PC), module
CVD/order-flow + zones de liquidation, squelette de skill "analyse".

## Interdit

Pas de live trading.
Pas dordre reel.
Pas de secrets dans Git.
Pas dactivation can_trade=True.
