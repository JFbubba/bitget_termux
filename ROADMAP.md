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

- Ajouter bootstrap_termux.sh
- Ajouter rotation des journaux
- Ajouter commande Telegram /git_version
- Ajouter verification de processus agent_loop.py
- Ajouter procedure restart propre

## Priorite 3  Observabilite

- Resume sante systeme
- Dernier commit Git
- Dernier tag stable
- Taille des journaux
- Nombre de pre-ordres pending/rejected/dry-run
- Statut pause/resume

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
