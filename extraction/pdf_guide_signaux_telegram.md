---
source: package/guide_recuperation_signaux_telegram.pdf
category: crypto-onchain
action: extracted
target: telegram_command_bot.py (notif), nouveau module `telegram_signal_listener`
---

## Sujet
Guide récupération de signaux depuis **canaux Telegram** (lecture, parsing).

## Valeur extraite
- Approches : bot membre du canal vs MTProto (Pyrogram/Telethon) en compte
  utilisateur — celle-ci permet de lire des canaux publics sans bot officiel.
- Parsing : regex robustes sur formats hétérogènes (symbol/entry/SL/TP), gestion
  des éditions et des suppressions.
- Risque : signaux **publics = sans edge** ; à n'utiliser que comme **proxy de
  sentiment** ou pour benchmarker nos signaux internes.

## Cible d'intégration
- Pas un nouveau moteur de signal — mais un **collecteur** read-only qui logge ce
  que les canaux disent et le **compare** ex-post à nos décisions (audit, anti-FOMO).
- `telegram_command_bot.py` est déjà côté **émission** ; ce module serait côté
  **réception**, à isoler pour ne pas confondre les rôles.
