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
- Ajouter procedure restart propre

## Priorite 3  Observabilite

- [x] Resume sante systeme (/system_health)
- [x] Dernier commit Git (/git_version)
- [x] Dernier tag stable (/git_version)
- Taille des journaux
- Nombre de pre-ordres pending/rejected/dry-run
- [x] Statut pause/resume (/pause_status)

## Priorite 4  Qualite strategie

- Backtest offline simple
- Journal des signaux ignores
- Statistiques par symbole
- Statistiques long/short
- Ratio TP/SL
- Gestion des signaux ambigus

## Interdit

Pas de live trading.
Pas dordre reel.
Pas de secrets dans Git.
Pas dactivation can_trade=True.
