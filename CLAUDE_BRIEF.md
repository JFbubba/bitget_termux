# Bitget Local AI Agent — Brief Claude PC

## Contexte

Le système tourne sur Termux Android dans ~/bitget-agent.

Claude PC n’a pas accès direct à Termux. Toute modification doit être proposée sous forme de patch ou de fichier, puis validée manuellement avant application.

## État actuel

Le système est un moteur local de monitoring / paper / dry-run pour Bitget futures.

Aucun ordre réel ne doit être envoyé.

## Pipeline actuel

1. journal_scanner.py
   - lit les marchés
   - calcule indicateurs
   - génère signaux

2. outcome_state.py
   - suit TP / SL
   - maintient open_outcomes_state.csv
   - maintient final_outcomes_journal.csv

3. order_signal_engine.py
   - transforme les signaux en propositions d’ordres
   - annote chaque proposition d’un score de confluence (order-flow + macro,
     advisory, fail-safe, n’écrase jamais le filtre sécurité)
   - écrit order_signals_report.txt

4. preorder_engine.py
   - transforme les signaux exploitables en pré-ordres verrouillés
   - écrit pending_orders.json

5. preorder_approval.py
   - approuve/refuse en simulation uniquement
   - écrit preorder_approvals_journal.jsonl

6. execution_gateway.py
   - simule une exécution en DRY_RUN_ONLY
   - écrit execution_dry_run_journal.jsonl
   - real_order_sent=false

7. telegram_command_bot.py
   - commandes Telegram :
     /status
     /config
     /config_guard
     /hub
     /agents
     /security
     /getagent_audit
     /signals
     /preorders
     /approve_preorder
     /approval_journal
     /dry_run_order
     /execution_journal
     /run_once
     /pause
     /resume
     /pause_status
     /help

8. security_agent.py
   - vérifie manifest
   - vérifie can_trade=False
   - scanne mots-clés dangereux
   - contrôle Telegram
   - vérifie GetAgent
   - verdict actuel : SAFE

## Interdictions

Ne jamais proposer de code qui exécute réellement :
- place_order
- open_long
- open_short
- close_position
- cancel_order
- change_leverage
- transfer
- withdraw

Ne jamais demander :
- BITGET_API_SECRET
- BITGET_API_PASSPHRASE
- TELEGRAM_BOT_TOKEN
- contenu .env

## Objectif de Claude

Auditer et améliorer le système sans connecter le trading réel.

Chercher :
1. bugs
2. incohérences
3. risques de sécurité
4. amélioration du scoring
5. tests unitaires
6. meilleure architecture
7. meilleure lisibilité Telegram
8. meilleur risk management
9. conditions préalables à un éventuel live trading borné

## Format attendu

Répondre avec :
- diagnostic
- risques
- patchs proposés
- fichiers à modifier
- tests à lancer
- aucun secret
- aucune exécution réelle
