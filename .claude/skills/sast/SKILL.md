---
name: sast
description: Scan SAST du code (analyse statique de securite) via semgrep en local, sans telemetrie. A utiliser quand on demande un scan de securite, une analyse statique, de chercher des vulnerabilites/failles, un audit de code semgrep, ou de verifier un fichier/module avant de le brancher. Lecture seule, jamais une porte de push.
---

# /sast — analyse statique de securite (semgrep, 100 % local)

Lance `sast_scan.sh` : appel EXPLICITE et manuel de semgrep (venv isole hors depot,
`/root/semgrep_venv`, ERR-004). Remplace le plugin semgrep « officiel » (hook global
opaque) reste DESACTIVE en fail-safe. **Le code ne quitte JAMAIS la machine** :
telemetrie coupee, pas d'appel reseau version, moteur OSS pur ; seules des regles
publiques entrent (cachees dans `~/.semgrep`). Lecture seule : n'execute aucun code du
bot, ne passe aucun ordre.

## Procedure
```bash
bash sast_scan.sh                                   # scan du depot (exclusions .semgrepignore)
bash sast_scan.sh scratchpad/mon_labo/ fichier.py   # cibles explicites (ex. avant de brancher un labo)
SAST_CONFIG="p/python p/secrets" bash sast_scan.sh  # jeu de regles au choix
```
Defaut : `p/python p/secrets p/command-injection`. Rapports dans `sast_out/`
(gitignored) : `semgrep_report.json` + `semgrep_summary.txt`. Le resume par finding
s'affiche aussi a l'ecran.

## Interpreter (INFORMATIF, jamais un blocage)
- Code de sortie : `0` = scan propre (avec ou sans findings), `>=2` = vraie erreur outil.
  Un finding N'EST PAS un echec de porte — **les 3 portes de push restent
  tests/security/safe_push** (`/safe-push`).
- Trier chaque finding : usage reellement sensible, ou faux positif ?
  - Hash a usage d'IDENTITE (cle de cache, dedup, empreinte de schema) = benin ->
    `usedforsecurity=False` (hashlib py3.9+) + au besoin `# nosemgrep: <rule-id>` cible,
    en documentant le pourquoi (cf. commit 23212e2 pour le modele).
  - Vrai probleme (injection, secret en dur, transport clair) -> corriger, puis rescanner.
- Les « erreurs moteur » (timeouts de regles taint sur `tests_audit.py`) sont cosmetiques.

## A NE PAS faire
- ❌ Cabler semgrep en **hook** ou **cron** : le plugin opaque a ete desactive EXPRES.
  Ce scan reste strictement A LA DEMANDE.
- ❌ Committer `sast_out/` (deja gitignored) ni traiter un finding comme feu vert pour
  desserrer un mur argent (les murs 50/250, levier x5, stop -5 % restent absolus).
- ❌ Installer semgrep dans le Python du bot (toujours le venv isole `/root/semgrep_venv`).

## Succes attendu
`sast_scan.sh` sort `0` ; resume lisible (`Findings: N`) affiche + ecrit dans
`sast_out/semgrep_summary.txt` ; baseline du depot attendue a **0 finding** (etat au
commit 23212e2). Si une correction de code a ete faite, relancer `/safe-push` avant push.
