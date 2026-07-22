---
name: installe-skill
description: Installer un skill/plugin externe (npx skills add, marketplace, dépôt GitHub) selon le rituel maison — installer, AUDITER le contenu (code exécutable, exfiltration, hooks), tester, consigner le hash dans skills-lock.json, verdict d'adoption. À utiliser pour « installe ce skill », « ajoute ce plugin », « npx skills add … », ou toute adoption d'outillage tiers.
---

# /installe-skill — installation + audit + verrouillage d'un skill tiers

Emballe le rituel pratiqué à la main 5 fois le 22/07 (python-testing-patterns,
impeccable, task-observer, claude-mem…). Un skill tiers est du CONTENU EXÉCUTÉ
dans le contexte d'un bot à argent réel : l'audit n'est pas optionnel.

## Procédure

### 1. Installer (portée demandée : projet ou global)
Commande du propriétaire si fournie (ex. `npx skills add <source>`), sinon la
voie standard du gestionnaire concerné. Noter la VERSION exacte installée.

### 2. Auditer AVANT d'adopter
- **Inventaire** : taille, types de fichiers. Markdown pur = risque faible ;
  scripts exécutables (.mjs/.js/.py/.sh) = examen ligne à ligne des motifs
  sensibles : réseau sortant (fetch/http/curl), lecture d'env/secrets, exec/eval,
  base64/obfuscation, écriture hors de son répertoire.
- **Hooks** : vérifier qu'AUCUN hook n'est câblé dans settings.json /
  settings.local.json sans décision explicite — un script livré reste INERTE
  tant qu'il n'est pas branché.
- **Appels sortants** : chaque endpoint identifié → le citer (URL, données
  envoyées, opt-out) et le signaler au propriétaire — jamais armé d'office.
- Outil d'appoint : `/sast` (semgrep local) sur les fichiers exécutables.

### 3. Tester sur le bot (lecture seule)
Un essai réel du skill sur un cas du dépôt, sans toucher au chemin-argent, pour
vérifier qu'il fait ce qu'il annonce.

### 4. Verrouiller
- Entrée dans `skills-lock.json` : source, version, hash des fichiers, date,
  verdict d'audit (motifs examinés, appels sortants, hooks).
- Activation : ON-DEMAND volontaire par défaut — PAS d'instruction
  d'auto-invocation ajoutée à CLAUDE.md sans décision propriétaire.

### 5. Consigner
Commit dédié (message français décrivant l'audit, jamais d'identifiant de
modèle), via `bash gates.sh && git add <fichiers> && git commit …`.

## Verdict type
« Installé <nom>@<version> (<portée>) — audit : <markdown pur | N scripts
examinés>, <0 | N> appel(s) sortant(s) signalé(s), aucun hook câblé,
hash consigné dans skills-lock.json. »
