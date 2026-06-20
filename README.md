0
# Bitget Termux Agent

Agent local Termux Android pour monitoring Bitget Futures en mode paper / dry-run uniquement.

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
