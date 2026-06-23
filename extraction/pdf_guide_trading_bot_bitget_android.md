---
source: package/Guide_Trading_Bot_Bitget_Android.pdf
category: bitget-tooling
action: extracted
target: README / OctoBot on Termux md (déjà présent), `pc/` setup
---

## Sujet
Guide bot Bitget sur **Android** (Termux + Python) — exactement le contexte du repo.

## Valeur extraite
- Astuces installation Termux/proot-distro pour Python 3.13, ccxt, cryptography.
- Variables d'environnement Bitget (key/secret/passphrase) + mode hedge vs one-way.
- Stratégies recommandées pour bot autonome longue durée (peu d'appels API,
  cache local, journalisation).

## Cible d'intégration
- Croiser avec `md_octobot_termux_nextrade.md` et `md_octobot_termux_short.md`
  (déjà présents dans `package/Markdown/`).
- Si le repo a un `pc/setup.md` ou équivalent, y consolider les commandes Termux.
- Pas de code à recopier, c'est de la doc d'installation.
