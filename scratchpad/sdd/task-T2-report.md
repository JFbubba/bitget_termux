# T2 — rapport d'implémentation : câbler replay_annuel -> champ `annuel` (porte §54 réelle)

## Ce qui a été fait

`agent_validation.replay_annuel()` (agent_validation.py:237) n'était jamais appelé en
production. `edge_ladder._annuel_ok(row)` (edge_ladder.py:111) lit `row["annuel"]["ic"]`
mais fail-open (retourne `True`, transparent) quand ce champ est absent — donc la porte
annuelle §54 (bloquer la promotion LIVE d'un agent dont l'IC sur 1 an d'historique est
négatif) était codée mais totalement inerte : ERR-013 (module câblé nulle part, jamais
consommé).

### Forme exacte du retour de `replay_annuel` (constatée en lisant agent_validation.py:237-279)

```python
replay_annuel(donnees=None, pas=24, horizon=8, warmup=80, agents=None)
# -> {agent_name: {"ic": float, "ic_t": float, "n": int}, ...}   si des données suffisantes
# -> {}                                                          si aucune donnée / échantillon < 50
```

`agent_name` correspond aux clés de `PURE_AGENTS` (`simons`, `savant`, `geometric`,
`divergent`) — les mêmes noms que la clé `"agent"` des lignes produites par
`rank_pure_agents` / `rank_pure_agents_xs` (agent_validation.py:436 et :535), donc la
jointure par nom est directe.

Si `donnees is None` (appel SANS argument — le seul cas de production), la fonction
consigne AUSSI la consultation au `holdout_registry` (agent_validation.py:247-257) avant
de charger `_panel_profond()` : c'est voulu, documenté dans le brief, et c'est pour ça
que le câblage NE DOIT JAMAIS pré-charger un panel et l'injecter à la place — ça
court-circuiterait la consignation d'hygiène anti-contamination du holdout.

### Fichiers modifiés

**`/root/bitget_termux_repo/brain_validation.py`**
- L34-49 : nouvelle fonction `_fuse_annuel(rows, annuel)` — PURE, ne mute PAS les dicts
  d'entrée (copie superficielle par ligne) ; fusionne `row["annuel"] = {"ic": <ic>}`
  uniquement pour les agents présents dans `annuel` (dict non-dict/incohérent -> traité
  comme `{}`, fail-safe).
- L52-67 : nouvelle fonction `_annuel_safe()` — best-effort ABSOLU : appelle
  `agent_validation.replay_annuel()` **sans argument** (consignation holdout voulue),
  retourne `{}` sur exception OU sur retour non-dict (incohérent), jamais de crash.
- L70-71 : `build_output(...)` gagne un paramètre optionnel `annuel=None`
  (signature RÉTRO-COMPATIBLE — exactement le pattern déjà utilisé pour `cpcv=None`).
- L101 : `"ranking": _fuse_annuel(ranked.get("agents", []), annuel)` au lieu de
  `ranked.get("agents", [])` brut.
- L90-94 : docstring de `build_output` étendue pour documenter le nouveau paramètre.
- L196-201 (`main()`) : `annuel = _annuel_safe()` puis passé à `build_output(...,
  annuel=annuel)` — même schéma d'appel que `cpcv = av.cpcv_diagnostic()` juste
  au-dessus (try/except déjà encapsulé dans `_annuel_safe`).
- L217-220 : ligne de log de `main()` enrichie (`+ annuel N agent(s) §54`) pour
  observabilité — sans quoi ce câblage serait lui-même un module « mesuré mais jamais
  visible » en production.

**`/root/bitget_termux_repo/tests_audit.py`** (insérés juste avant `def _run_all():`,
comme demandé, après `test_cpcv_gate_armee_bride_sur_preuve`)
- `test_annuel_fusion_ranking_et_porte_edge_ladder` (L14074+) : monkeypatch de
  `agent_validation.replay_annuel` (retour SYNTHÉTIQUE, aucun réseau/holdout réel,
  ERR-019), vérifie que `_annuel_safe()` restitue le dict, que `build_output` fusionne
  `row["annuel"]["ic"]` pour les agents présents (et PAS pour un agent absent du
  retour), que `ranked["agents"]` original n'est pas muté, et que
  `edge_ladder.all_tiers` bride bien un IC annuel négatif (LIVE -> PROBATION) tout en
  laissant passer un IC positif et un agent absent (fail-open, LIVE inchangé).
- `test_annuel_echec_replay_annuel_pas_de_crash` (L14119+) : `agent_validation.replay_annuel`
  monkeypatché pour lever une exception -> `_annuel_safe()` retourne `{}` sans crash,
  le rapport fusionné reste sans champ `annuel`, la porte reste fail-open (comportement
  identique à avant ce câblage), la signature reste rétro-compatible (appel sans le
  paramètre `annuel`), et un retour INCOHÉRENT (liste au lieu d'un dict) est traité de
  la même façon (fail-safe, pas seulement les exceptions).

**`docs/VERDICTS.md`** : entrée existante « CPCV multi-chemins + registre d'usage du
holdout » (ligne ~91, section ÉVALUÉ) complétée avec le paragraphe « TROU FERMÉ le
21/07 (soir, T2) » — c'est la continuation directe de cette livraison, qui avait câblé
`cpcv_diagnostic` et `holdout_registry` mais laissé `replay_annuel` non appelé en
production.

**`scratchpad/LABOS.md`** : nouvelle ligne `porte_annuelle_54` (à la suite de
`cpcv_promotion`/`holdout_registry`, même style « DANS le dépôt, pas un labo »).

### Ne PAS touché (conforme aux bornes du brief)
`edge_ladder.py`, `parity_harness.py`, `lab_scenarios.py`, `config.py`,
`.claude/agents/*.md`, aucun mur/garde/kill-switch. `docs/BACKLOG_RECHERCHE.md` avait
une modification pré-existante non commitée (session antérieure) que je n'ai PAS
touchée et que je ne stage pas.

## Coût mesuré (item 3 du brief)

Mesure directe (script manuel, hors tests, sur le panel profond RÉEL —
`candles_history` BTC/ETH/SOL/XRP en 1h, ~6 ans, 43-50k bougies/symbole) :

| Étape | Durée |
|---|---|
| `_panel_profond()` (chargement disque) | 0,205 s |
| `replay_annuel(donnees=panel)` | 204,0 s |
| `cpcv_diagnostic(donnees=panel)` (pour comparaison — déjà en prod) | 266,8 s |

`replay_annuel` coûte donc à peu près le même ordre de grandeur que `cpcv_diagnostic`
qui tourne déjà sans problème sur la cadence 6h (`bitget-validation.timer`,
`MIN_INTERVAL_H=5.5`). Ajouter ~204 s à un cycle de validation qui dure déjà plusieurs
minutes est négligeable à l'échelle de 6h (< 1 % du budget de cadence). **Partage de
calcul avec `cpcv_diagnostic` jugé NON pratiquable sans refactor lourd** : les deux
fonctions rejouent indépendamment les mêmes agents purs sur le même panel (boucle
`fn(candles[...])` quasi identique), mais (a) fusionner ces boucles demanderait de
faire remonter la logique de fenêtrage (`pas_eff`, `warmup`, `horizon`) d'une fonction
dans l'autre — refactor non trivial hors du périmètre « minimal mais correct » de la
tâche — et surtout (b) `replay_annuel()` DOIT être appelée **sans argument** pour que la
consignation du holdout ait lieu (agent_validation.py:247-257) ; lui injecter un panel
pré-chargé en commun avec `cpcv_diagnostic` supprimerait cette consignation. **Décision :
accepter le coût, documenté dans le docstring de `_annuel_safe` et dans
`docs/VERDICTS.md`/`scratchpad/LABOS.md`.**

Résultat RÉEL constaté (à titre indicatif — mesure de coût, PAS un verdict d'edge, PAS
consommé pour tuner quoi que ce soit) : `simons` ic=0,011 (t 0,44), `savant` ic=0,034
(t 1,35), `geometric` ic=−0,003 (t −0,12), `divergent` ic=0,004 (t 0,14), n=1608
chacun. **Correction post-revue (21/07)** : geometric porte un IC annuel NÉGATIF —
`_annuel_ok(geometric)=False` dès aujourd'hui, donc la porte annuelle est DÉJÀ ACTIVE
contre lui (LIVE serait retenu pour geometric s'il franchissait un jour le replay) ;
elle est muette pour les 3 autres uniquement parce qu'AUCUN des 4 agents purs ne passe
encore le replay (DSR<0,90 pour les quatre dans le rapport de production actuel) — ce
n'est PAS l'absence d'IC annuel négatif qui la rend silencieuse (l'affirmation initiale
« aucun IC annuel n'est négatif aujourd'hui » était fausse). Origine de cette mesure :
**backtest** sur données réelles injectées manuellement via `donnees=panel` (donc SANS
consignation au holdout registry — ce n'était pas la consultation officielle de
production, seulement une mesure de coût/plausibilité).

## TDD

Avant d'écrire le code, les deux tests ont été rédigés puis vérifiés en échec : `git
stash push -m TDD-check-T2 -- brain_validation.py` (implémentation retirée), exécution
directe des deux fonctions de test -> `AttributeError: module 'brain_validation' has no
attribute '_annuel_safe'` pour les deux -> confirmé qu'ils échouent bien SANS
l'implémentation. `git stash pop` a restauré le code, puis les deux tests ont été
réexécutés et passent.

## Auto-revue effectuée

- Vérifié qu'aucun autre appelant de `build_output(...)` n'existe dans le dépôt (un
  seul site d'appel, dans `main()`) — le changement de comportement (copies de dicts
  au lieu des mêmes objets dans `ranking`) est donc sans risque de régression
  d'identité ailleurs.
- Durci `_fuse_annuel` et `_annuel_safe` contre un retour **incohérent** (pas
  seulement une exception) — `replay_annuel` renvoie toujours un dict par contrat,
  mais le brief exige explicitement « indispo/lent/incohérent -> ignoré » ; test dédié
  ajouté pour ce cas (retour liste au lieu de dict).
- Vérifié que `ranked["agents"]` (l'objet passé par l'appelant) n'est jamais muté par
  `_fuse_annuel` (test dédié `assert all("annuel" not in r for r in ranking)`).
- Vérifié la rétro-compatibilité : `build_output(...)` appelée SANS le nouveau
  paramètre produit un `ranking` identique à l'appel avec `annuel={}`/`None` (test
  dédié).

## Résultats des tests

- Les deux (puis trois assertions dans le second test) nouveaux tests passent
  **isolément** (`python3 -c "import tests_audit as t; t.test_annuel_...()"`).
- Suite complète : `python tests_audit.py` -> **712/712 tests OK** (710 avant +2
  nouvelles fonctions de test).
- `bash gates.sh` -> **3 portes vertes** (tests_audit 712/712, security_agent VERDICT:
  SAFE, safe_push_check.sh OK), rejoué deux fois après un durcissement fail-safe
  mineur (retour incohérent) pour confirmer la non-régression.
- `graphify update .` exécuté après les modifications (6878 nœuds, 11332 arêtes, 580
  communautés).

## Réserves

- La porte §54 est maintenant réelle et **DÉJÀ ACTIVE contre geometric** (ic annuel
  −0,003, négatif → `_annuel_ok(geometric)=False`) : LIVE serait retenu pour lui s'il
  franchissait un jour le replay. Elle reste muette EN PRATIQUE aujourd'hui pour
  l'ENSEMBLE des 4 agents purs uniquement parce qu'aucun ne passe encore le replay
  (DSR<0,90) — pas parce qu'aucun IC annuel ne serait négatif (**correction post-revue
  du 21/07** : l'affirmation initiale du présent rapport était fausse, corrigée
  ci-dessus et dans `docs/VERDICTS.md`/`scratchpad/LABOS.md`).
- Le coût (~204 s/run, un ordre de grandeur avec `cpcv_diagnostic`) est accepté sur la
  cadence 6h ; si un futur ajout similaire s'empile sur le même timer, il faudra
  reconsidérer un partage de calcul plus profond (probablement en factorisant la boucle
  de fenêtrage votes/fwd hors des deux fonctions) — non fait ici pour rester dans le
  périmètre « minimal mais correct ».

## Correctifs post-revue adversariale (21/07, soir)

Quatre correctifs appliqués en deux commits, timer `bitget-validation.timer` suspendu
avant l'édition de `brain_validation.py`/`agent_validation.py` et relancé après le
dernier commit (application d'ERR-022, voir ci-dessous).

### Correctif 1 — affirmation fausse « aucun IC annuel négatif aujourd'hui »

`docs/VERDICTS.md`, `scratchpad/LABOS.md` et le présent rapport affirmaient qu'aucun IC
annuel n'était négatif aujourd'hui. **Faux** : `validation_report.json` porte
`geometric {'ic': -0.003}` → `edge_ladder._annuel_ok(row_geometric)` retourne `False`
dès maintenant (vérifié directement : `float(-0.003) > 0.0` est faux). Corrigé dans les
3 emplacements : la porte annuelle est DÉJÀ ACTIVE contre `geometric` (elle retiendrait
LIVE pour lui s'il franchissait un jour le replay DSR/n/OOS) ; elle est muette pour les
3 autres (simons/savant/divergent, ic tous positifs) uniquement parce qu'AUCUN des 4
agents purs ne passe encore le replay (DSR<0,90 pour les quatre dans le rapport de
production actuel) — ce n'est pas l'absence d'IC annuel négatif qui la rend silencieuse.

### Correctif 2 — journal ERR-022 (timer actif pendant l'édition)

`docs/AGENT_ERRORS.md` : nouvelle entrée. Note de numérotation : la tâche demandait
« ERR-020 », mais `ERR-020` et `ERR-021` étaient déjà pris par deux incidents distincts
du 20/07 (constatés en listant les entrées existantes AVANT d'écrire — cf. ERR-003/
ERR-015, ne jamais supposer sans vérifier) ; la règle du journal (« ne jamais effacer/
réutiliser une entrée ») impose de poursuivre la numérotation séquentielle → livrée en
**ERR-022**. Contenu : le timer `bitget-validation.timer` a tiré à 21:01 pendant
l'édition de `brain_validation.py`, exécutant un état intermédiaire du working tree non
commité (rapport fusionné + consignation holdout horodatés avant le commit) —
inoffensif cette fois, scénario d'échec documenté (fichier à moitié édité → rapport
corrompu lu par `edge_ladder`/`mandate`). Contrôle : suspendre le timer avant d'éditer
un fichier qu'il consomme, vérifier après coup l'horodatage des artefacts produits
pendant la fenêtre d'édition. Appliqué dans cette même session (timer suspendu avant
d'éditer `brain_validation.py`/`agent_validation.py`, relancé après le commit B).

### Correctif 3 — sémantique du drapeau `contamine` (commit séparé)

`holdout_registry.consigner(..., mode="recherche")` (défaut CONSERVATEUR) ;
`agent_validation.replay_annuel(..., consultation="recherche")` transmis à
`consigner` ; `brain_validation._annuel_safe()` (seul appelant automatisé) passe
`consultation="gate_auto"`. `statut()` : `contamine=True` seulement si >1 consultation
de la MÊME version en mode "recherche" ; `par_mode` (compte par mode) + `consultations`
(compte total) exposés ; entrées sans champ `mode` (registre pré-existant) comptent
comme "recherche" (rétro-compatible, conservateur). Sans ce correctif, le tir planifié
toutes les 6h aurait rendu `contamine=True` en PERMANENCE dès le 2e tir sur la même
version, vidant le drapeau de toute valeur diagnostique.

### Correctif 4 — `_fuse_annuel` ignore un ic non numérique (fail-open)

`brain_validation._fuse_annuel` ne fusionne `row["annuel"]` que si
`isinstance(info.get("ic"), (int, float))` ET pas un `bool` (un `bool` est une
sous-classe d'`int` en Python — exclu explicitement). Un ic non numérique (chaîne,
`None`, `bool`, régression amont) n'est jamais propagé vers le `float()` de
`edge_ladder._annuel_ok`, qui resterait sinon exposé à un `TypeError`/`ValueError`
selon le type reçu.

### Tests couvrants exécutés

- `python3 -c "import tests_audit as t; t.test_holdout_registry_contamination_et_fail_safe(); t.test_replay_annuel_consultation_mode_forwardee_a_holdout_registry(); t.test_annuel_fusion_ranking_et_porte_edge_ladder(); t.test_annuel_echec_replay_annuel_pas_de_crash()"`
  → `OK 1` / `OK 2` / `OK 3 (annuel wiring toujours vert)` / `OK 4` (les 4 exécutés
  isolément, avant intégration à la suite).
- `bash gates.sh` avant le commit A (correctifs 1+2+4) : `712/712 tests OK` ·
  `VERDICT: SAFE` · `SAFE PUSH CHECK OK` · `=== 3 PORTES VERTES ===`.
- `bash gates.sh` avant le commit B (correctif 3, +1 nouveau test
  `test_replay_annuel_consultation_mode_forwardee_a_holdout_registry`) :
  `713/713 tests OK` · `VERDICT: SAFE` · `SAFE PUSH CHECK OK` · `=== 3 PORTES VERTES ===`.
- `graphify update .` exécuté après le commit B (6882 nœuds, 11336 arêtes, 584
  communautés).

### Commits (2, non poussés)

- Commit A (`409f44e`) : correctifs 1+2+4 — docs/VERDICTS.md, scratchpad/LABOS.md,
  scratchpad/sdd/task-T2-report.md (correctif 1) ; docs/AGENT_ERRORS.md (ERR-022,
  correctif 2) ; brain_validation.py `_fuse_annuel` (correctif 4).
- Commit B (`99d46de`) : correctif 3 — holdout_registry.py, agent_validation.py
  (`replay_annuel`), brain_validation.py (`_annuel_safe`), tests_audit.py (2 tests).

### Ne PAS touché (conforme aux bornes du correctif)

`edge_ladder.py`, `parity_harness.py`, `lab_scenarios.py`, `config.py`, aucun mur/garde/
kill-switch. `docs/BACKLOG_RECHERCHE.md`/`docs/RESEARCH_NOTES.md` (modifications
pré-existantes non commitées d'une session antérieure) toujours non touchées/non
stagées. Le timer `bitget-validation.timer` a été suspendu avant l'édition de
`brain_validation.py`/`agent_validation.py` (correctifs 1/3/4) et relancé après le
commit B — vérifié actif (`systemctl is-active` → `active`).
