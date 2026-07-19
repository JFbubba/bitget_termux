---
name: lance-correction
description: Analyse COMPLÈTE du bot à la recherche d'erreurs (méthode + code + santé), via l'agent autodidacte/autocorrecteur + les moniteurs. Déclenché quand le propriétaire dit « lance correction » (ou « lance la correction », « corrige le bot », « cherche les erreurs »). Lecture seule d'abord ; corrige ce qui est clairement corrigeable, dans les 3 portes.
---

# /lance-correction — analyse complète du bot à la recherche d'erreurs

Balayage exhaustif et LECTURE SEULE du dépôt, puis correction de ce qui est clairement
corrigeable. Réunit l'agent autocorrecteur (`autodidacte.py`) et les moniteurs existants.
Aucun ordre, aucun secret. Toute correction passe les **3 portes** avant commit ; le push
reste explicite. Chaque nouvelle erreur découverte → une entrée dans `docs/AGENT_ERRORS.md`.

## Procédure

### 1. Auto-correcteur — erreurs de MÉTHODE (récurrences du journal)
```bash
python autodidacte.py
```
- Bras AUTOCORRECTEUR : signale les récurrences automatisables (ex. **ERR-001** listes de
  timeframes incomplètes). Toute ligne signalée = vrai bug à corriger OU config
  opérationnelle légitime à annoter `# tf-ladder-ok : <raison>`.
- Bras AUTODIDACTE : savoir (`knowledge_base`) vs mesuré (`strategies_out`).

### 2. Intégrité du CODE — les 3 portes
```bash
python tests_audit.py        # doit finir N/N tests OK
python security_agent.py     # doit afficher VERDICT: SAFE
bash safe_push_check.sh      # doit finir SAFE PUSH CHECK OK
```
Un test rouge / un WARNING = une erreur à investiguer et corriger.

### 3. Santé SYSTÈME & APPRENTISSAGE (lecture seule)
```bash
python system_health.py      # fichiers manquants, journaux périmés, compteurs
python learning_health.py    # alignement poids↔cible + garde pearson (§96), corr hit-rate↔IC
python watchdog.py           # liveness des timers brain/scan (SANS --heal ici : lecture seule)
```
Signaler : artefacts figés/anciens, désalignement d'apprentissage, timer mort.

### 4. Revue de JUGEMENT (les erreurs non automatisables du journal)
Lire `docs/AGENT_ERRORS.md` et repasser à la main les contrôles de jugement :
- **ERR-002** — un système conçu comme un TOUT (séquence/machine à états) est-il testé/
  implémenté entier et dans l'ordre, pas décomposé en filtres indépendants ?
- **ERR-003** — les affirmations factuelles récentes sont-elles vérifiées contre le système
  réel (API/config), pas supposées ?
- **ERR-015** — AVANT de construire un correctif/module, l'existant a-t-il été vérifié ?
  `python prior_art.py "<concept>"` (ou l'agent `prior-art-scout`) : « CODE EXISTANT » ⇒ étendre,
  ne pas re-coder ; « DÉJÀ MESURÉ » ⇒ lire le verdict, ne pas re-tester (double data).
- **ERR-016** — une mesure classe-t-elle bien l'INTENTION du module ? Un outil de RECONNAISSANCE
  de structure / d'aide à l'EXÉCUTION (« où suis-je dans le mouvement ») ne se juge PAS à une IC
  directionnelle mais à la qualité de PLACEMENT/exécution (fill, markout).

### 5. Consolider & agir
- Produire un **verdict consolidé** : ce qui est vert, ce qui est signalé, par sévérité.
- **Corriger** les vrais bugs clairement corrigeables (annoter les cas légitimes). Toute
  correction : relancer les 3 portes, commit clair en français (aucun identifiant de modèle),
  push explicite seulement si demandé.
- **Journaliser** toute NOUVELLE classe d'erreur dans `docs/AGENT_ERRORS.md` (Contexte ·
  Cause racine · Solution · Contrôle · Statut) + pointeur mémoire si comportemental.
- Rester dans les murs : murs argent (50/250, ×5…), stop −5 %, mesure-d'abord, retrait
  inexistant — jamais desserrés par une « correction ».
