---
name: fin-de-session
description: Clôture de session en UN aller-retour — trier les artefacts, préserver ce qui doit l'être, passer les portes, committer/pousser, régénérer le dashboard, puis donner le feu vert « tu peux clear ». À utiliser quand le propriétaire demande « je peux clear ? », « prépare le clear », « clôture la session », « committe et pousse avant clear », « fin de session ».
---

# /fin-de-session — clôture propre en un aller-retour

Remplace le ballet mesuré 5+ fois par l'audit du 22/07 : « je peux clear ? » →
« il reste des fichiers » → « préserve-les » → « pousse » → « mets le dashboard à
jour ». Ici tout s'enchaîne, et la réponse finale est OUI ou NON avec la raison.

## Procédure (dans l'ordre, s'arrêter à la première anomalie bloquante)

### 1. Inventaire du working tree
```bash
git status --porcelain
```
Classer chaque entrée :
- **À committer** : code/doc/tests légitimes de la session (liste NOMINATIVE —
  jamais `git add -A`, le hook guard.py le bloque).
- **À préserver hors dépôt** : artefacts de labo/scratchpad utiles → les déplacer
  vers leur place durable (docs/, tests/, ou mémoire) AVANT le commit.
- **À jeter** : .bak, fichiers temporaires, sorties de debug — supprimer après
  vérification rapide du contenu (ne jamais supprimer un fichier non identifié :
  le signaler à la place).

### 2. Vérifications de sécurité de fin de session
- Aucun secret dans les fichiers à committer (`grep` ciblé si doute).
- Aucun ARMEMENT mêlé à un commit de logique (hygiène d'armement CLAUDE.md §5) —
  si un verrou/cap a changé, commit ISOLÉ.
- Timers/démons : si un fichier édité est consommé par un timer actif (ERR-022),
  vérifier que l'édition est terminée et l'état cohérent.

### 3. Les portes puis le commit
```bash
bash gates.sh && git add <fichiers nominatifs> && git commit -m "<message français, sans identifiant de modèle>"
git push
```
Forme OBLIGATOIRE : `gates.sh` en tête de chaîne `&&` (codes de sortie stricts).
Une porte rouge = STOP, montrer la sortie, corriger, relancer.

### 4. Dashboard / Artifact (si la session a touché l'affichage ou l'état)
```bash
python scratchpad/render_dashboard.py
```
puis redéployer l'Artifact cockpit habituel (cf. mémoire dashboard-artifact-cockpit).
Sauter cette étape si rien de visible n'a changé (le dire explicitement).

### 5. Verdict
- **« ✅ Tu peux clear »** : working tree propre, push fait, dashboard à jour,
  + une ligne de résumé de ce qui a été préservé/committé.
- **« ⛔ Pas encore »** : la raison exacte (porte rouge, fichier non identifié,
  push refusé) et ce qu'il faut décider.

## À NE PAS faire
- Ne jamais pousser du rouge « pour finir vite » — les portes priment sur le clear.
- Ne jamais supprimer un fichier qu'on ne peut pas identifier — le lister au verdict.
- Ne pas lancer de cycle réel (accumulation/futures) pendant la clôture.
