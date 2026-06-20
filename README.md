# Bitget Termux Agent

Agent local Termux Android pour monitoring Bitget Futures en mode paper / dry-run uniquement.

> Référence complète des commandes Termux : voir [TERMUX.md](TERMUX.md).

## Architecture (2 machines)

- **Termux (Android)** — ce dépôt : moteur de monitoring **paper / dry-run**,
  collecte / analyse / envoi de signaux. Reste `can_trade=False`, aucun ordre réel.
- **PC (Claude Code + Bitget Agent Hub)** — pont MCP vers l'exchange Bitget,
  capable de trading réel. Installation : voir [pc/BITGET_AGENT_HUB.md](pc/BITGET_AGENT_HUB.md).

## Etat stable

- Tag stable : stable-paper-dryrun-20260620
- Branche : main
- Commit stable : 1a1f811d60136063494949cd5ee3d702d741c7c9
- Mode obligatoire : paper / dry-run only
- Aucun ordre reel
- Tous les agents : can_trade=False
- Etat valide : VERDICT SAFE, HEALTH OK, tests_audit.py 15/15 OK

## Securite

Ne jamais versionner :

- .env
- cles Bitget
- token Telegram
- chat_id complet
- journaux runtime
- fichiers CSV runtime
- fichiers JSONL runtime
- etats locaux paper

Ne jamais activer :

- place_order
- open_long
- open_short
- close_position
- cancel_order
- change_leverage
- transfer
- withdraw

## Repertoires locaux

- Moteur local Termux : ~/bitget-agent
- Repo GitHub propre : ~/bitget_termux_repo

## Commandes utiles

```bash
python tests_audit.py
python security_agent.py
python agent_hub.py
python agent_control.py
python git_version.py
python system_health.py
python watchdog.py
python stats_report.py
```

## Exploitation Termux

```bash
bash bootstrap_termux.sh   # installe les dependances (requirements.txt)
bash restart_agent.sh      # arret propre + relance de agent_loop.py
bash rotate_logs.sh        # rotation avancee des journaux (gzip + retention KEEP)
MAX_KB=1024 KEEP=14 bash rotate_logs.sh   # seuil et retention configurables
bash safe_push_check.sh    # controle avant git push (secrets, ordres, tests)
```

## Commandes Telegram (lecture seule)

- /git_version : commit, branche, dernier tag, etat du depot
- /system_health : bilan de sante (fichiers, fraicheur, can_trade=False, pause)
- /watchdog : etat de la boucle agent_loop (PID, /proc, fraicheur du scan)
- /stats : statistiques TP/SL par symbole et sens (resultats finalises)
- /security : audit securite (VERDICT SAFE attendu)
- /status : rapport compact
