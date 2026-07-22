---
name: ingest-bundle
description: Trier un GROS pavé de texte collé (brouillon, recherche, méthode trouvée sur le net, liste de prompts/stratégies) contre TOUT l'existant du bot — mémoire, verdicts, savoir, code — et n'appliquer QUE le delta, en additif, sans doublon. À utiliser dès qu'un message contient un long contenu collé avec une intention type « analyse tout ça », « intègre le meilleur », « duplique ce qui est utile », « je ne sais plus ce que je t'ai déjà envoyé ».
---

# /ingest-bundle — triage d'un pavé collé contre l'existant

Motif mesuré 5+ fois par l'audit du 22/07 : le propriétaire re-colle des brouillons
volumineux sans se souvenir de ce qui a déjà été traité. Le protocole manuel qui a
fait ses preuves (bundles des 19–21/07) devient ici la procédure standard. Règle
d'or : **tout apport externe s'applique en ADDITIF — carte anti-doublon d'abord,
jamais de suppression.**

## Procédure

### 1. Découper le pavé en CLAIMS
Lister les idées/demandes distinctes du pavé (stratégie, indicateur, architecture,
outil, fait API, règle fiscale…) — une ligne par claim. C'est la maille du triage.

### 2. Charger la carte anti-doublon (lecture seule)
Dans cet ordre — s'arrêter dès qu'un claim est résolu :
1. **Mémoire** : `MEMORY.md` + fiches pertinentes (surtout la section « Verdicts
   de mesure (NE PAS re-tester) » et les fiches `bundle-*-triage`,
   `draft-bundle-already-covered`).
2. **Verdicts & savoir du dépôt** : `docs/VERDICTS.md`, `docs/SAVOIR.md`,
   `docs/BITGET_REFERENCE.md`, `docs/OS_MAPPING.md` (carte anti-doublon des
   apports « OS »), `docs/AGENT_ERRORS.md`.
3. **Code existant** : `graphify query "<concept>"` puis `python prior_art.py
   "<concept>"` (ERR-015) — un module peut déjà exister sous un autre nom
   (leçon smc.py).

### 3. Classer chaque claim
- **DÉJÀ COUVERT** : module/verdict existant → citer OÙ (fichier/§). Ne rien refaire.
- **DÉJÀ REJETÉ** : mesuré négatif → citer le verdict. Ne PAS re-mesurer (double data).
- **DELTA** : véritablement nouveau → le décrire en une ligne + où il irait.
- **CONTREDIT L'EXISTANT** : le signaler explicitement (ne pas écraser un verdict
  mesuré par une opinion collée).

### 4. Livrer le tri AVANT d'agir
Tableau claims → statut → référence. Puis SEULEMENT pour les DELTA : proposer
l'action (backlog, labo de mesure, doc) — mesure-d'abord, gated OFF par défaut,
et poser la question de portée (« advisory ou armé ? un symbole ou l'univers ? »)
à la conception.

### 5. Consigner
Si le tri a demandé un vrai travail : fiche mémoire `bundle-*-triage` (une ligne
dans MEMORY.md) pour que le PROCHAIN collage du même brouillon coûte zéro.

## À NE PAS faire
- Re-tester une idée de la section « Verdicts (NE PAS re-tester) ».
- Transformer « fouille/pioche des idées » en installation/audit d'adoption complet.
- Supprimer ou réécrire de l'existant au motif que le pavé le refait « mieux ».
