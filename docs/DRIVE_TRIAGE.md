# Triage du dossier Drive « trading/package »

> Mission : analyser **chaque fichier** du fourre-tout `package/` (docs, sources,
> PDF, skills, projets entamés…) sans rien retraiter deux fois et sans se perdre.
> Le suivi est tenu par `drive_triage.py` (+ `drive_triage.json`).

## Objectif par fichier (rubrique d'analyse)
1. **Identifier** : titre, type, dossier, **sujet** normalisé.
2. **Doublons** : croiser par **sujet** (`subject_duplicates`) et par **hash de
   contenu** (`hash_duplicates`) → ne pas réextraire ni recréer un doublon.
3. **Pertinence** : utile à *notre* projet (cerveau / agents / dashboard / risque) ?
4. **Action** :
   - `learned` — extraire la **valeur pédagogique** → l'intégrer au cerveau
     (`docs/RESEARCH_NOTES.md`, nouveaux §) ou aux compétences d'un agent.
   - `extracted` — extraire des infos/données réutilisables.
   - `tool-adapted` — si c'est un **outil** : vérifier son utilité et s'il n'est
     pas **déjà** présent sous une autre forme ; si utile, **copier/adapter** la
     config à notre usage (dans le repo).
   - `skipped` — hors-sujet / obsolète / doublon.
5. **Marquer** `status="traité"` dans le registre **avant** de confirmer.

## Ordre de passage
1. **PDF d'abord** (`mimeType = application/pdf`) — sources pédagogiques denses
   pour optimiser le cerveau, les agents, et la lecture rapide du croisement de
   données.
2. Puis code / skills / configs (outils → évaluer/adapter).
3. Puis docs/notes diverses.

## Registre (`drive_triage.py`)
- `is_processed(reg, id|title)` — **vérifier avant de confirmer « traité »**.
- `upsert(reg, entry)` — ajout/maj idempotent par `id` (ne clobbe pas le statut).
- `subject_duplicates` / `hash_duplicates` — anti-doublon.
- `counters` — **traités / total**, dossiers, PDF, pertinents, par action.
- `python drive_triage.py` — rapport ; `… check <id|titre>` — statut d'un fichier.
- Le registre vit **dans le repo** (versionné, fiable, modifiable en place) — le
  serveur Drive est éphémère/sans mise à jour en place, et son stockage est limité.

## Accès aux fichiers (deux voies)
- **MCP Google Drive (depuis cette session distante)** : lecture/recherche/
  download + create/copy. **Pas de move/delete/rename.** Suffit pour *analyser et
  apprendre* ; pas pour *réorganiser*.
- **Montage local + Claude Code local** (Drive Desktop sur Win/Mac, ou `rclone
  mount` sur Linux/Termux) : les fichiers deviennent de **vrais fichiers locaux**
  → accès complet (read/grep/**move/rename/delete**) via les outils fichiers. C'est
  la voie pour *réorganiser*. (Ne s'applique pas à la session cloud actuelle, qui
  est isolée de ta machine.)

## Vie privée
Le registre stocke les **titres** de tes fichiers Drive dans le repo
`bitget_termux`. Si le repo est public ou que tu préfères, on peut le **gitignorer**
(au prix de la persistance entre sessions) ou le chiffrer/anonymiser.
