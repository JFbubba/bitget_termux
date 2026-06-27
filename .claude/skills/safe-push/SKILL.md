---
name: safe-push
description: Lance les 3 portes obligatoires (tests_audit.py, security_agent.py, safe_push_check.sh) avant tout git push. A utiliser avant de pousser, quand on demande de pousser/committer, ou pour verifier que le depot est pret a pousser.
---

# /safe-push — les 3 portes avant tout push

Applique la regle d'engagement #5 de CLAUDE.md : **aucun push tant que les 3 portes
ne sont pas vertes**. Lecture seule : n'ecrit rien, ne pousse rien tout seul.

## Procedure (s'arreter a la PREMIERE qui echoue)

1. **Tests**
   ```bash
   python tests_audit.py
   ```
   Doit finir sur `N/N tests OK`. Sinon : ne pas pousser, rapporter les tests rouges.

2. **Audit securite**
   ```bash
   python security_agent.py
   ```
   Doit afficher `VERDICT: SAFE`. Sinon : ne pas pousser, rapporter ce qui est flagge.

3. **Garde push**
   ```bash
   bash safe_push_check.sh
   ```
   Doit finir sur `SAFE PUSH CHECK OK`. Interdit notamment du code d'ordre hors de
   `spot_executor.py` (scan `*.py`) et tout fichier secret/runtime tracke.

## Si les 3 sont vertes
- Annoncer : « 3 portes vertes — pret a pousser ».
- **Ne PAS pousser automatiquement.** Le push reste une action explicite du proprietaire
  (CLAUDE.md), sur la branche `claude/...`, jamais `main`.
- Rappel commit : message en francais, **aucun identifiant de modele** dans le commit/PR.

## Si une echoue
- Stopper, montrer la sortie de la porte rouge, proposer un correctif, puis relancer
  `/safe-push` apres correction.
