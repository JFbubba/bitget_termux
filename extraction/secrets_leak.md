---
source: G:/Mon Drive/Trading/package/{xcom.md, token github.txt, SMSPool_Account_6283598794835383.txt, OctoBot.git-*, OctoBot-Trading.git-*, OpenBB.git-*, TradingAgents.git-*}
category: secret-leak
action: extracted
target: (hors repo) — rotation immédiate + nettoyage Drive
---

## ⚠️ CRITIQUE — clés / tokens en clair dans `package/`

Le fichier `xcom.md` à la racine de `package/` contient en clair :

- bearer token + clé/secret consommateur **X / Twitter API**
- ID + secret **client OAuth 2.0 X**
- clé **xAI** (`xai-…`)
- clé **Anthropic** (`sk-ant-api03-…`)
- token **bot Discord**
- clé API **Hostinger** + bloc `mcpServers` Hostinger

Autres fichiers à risque :
- `token github.txt` (93 octets — quasi sûrement un PAT GitHub)
- `SMSPool_Account_6283598794835383.txt` (compte SMSPool)
- les blocs `*.git-*` extraits (config, packed-refs, logs) — peuvent fuiter des
  remotes privés ou des chemins locaux

## Pourquoi c'est pertinent pour nous

Drive Desktop est synchronisé sur la machine, et ce dossier est régulièrement scanné
par des agents. Toute clé qui transite par un LLM (chez Anthropic, OpenAI, autre)
doit être considérée comme **compromise** dès qu'elle est lue en contexte.

## Cible / action

- **Hors repo** : `extraction/` n'embarque AUCUNE des valeurs (volontairement).
- **À faire côté utilisateur, MAINTENANT** :
  1. Révoquer / régénérer **chaque** clé listée ci-dessus chez son fournisseur.
  2. Supprimer ou chiffrer `xcom.md`, `token github.txt`, `SMSPool_Account_*.txt`
     dans le Drive (et vider la corbeille).
  3. Si le compte X / Anthropic / xAI / Discord / Hostinger a des logs d'usage,
     vérifier l'absence d'activité non reconnue depuis la création des clés.
  4. Centraliser les secrets dans un store dédié (`.env` local + `secrets/` gitignoré,
     ou gestionnaire type 1Password / Bitwarden).

## Lien avec DRIVE_TRIAGE

Ce point n'est pas du « learned / extracted / skipped » classique : c'est un
**garde-fou sécurité** qui passe avant tout triage. Aucune passe d'analyse ne doit
recopier le contenu de ces fichiers dans le repo ni le coller dans un prompt.
