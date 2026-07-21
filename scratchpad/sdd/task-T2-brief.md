# T2 — câbler replay_annuel -> champ `annuel` du rapport de validation (porte §54 réelle)

## Constat (vérifié)
- `edge_ladder._annuel_ok(row)` lit `row["annuel"]["ic"]` dans les lignes de `ranking` de
  `validation_report.json` ; FAIL-OPEN si absent. Or `agent_validation.replay_annuel` n'est
  JAMAIS appelé en production -> le champ `annuel` n'existe dans aucune ligne -> la porte
  annuelle §54 est transparente en pratique ET la consignation holdout (début de
  replay_annuel) ne tourne jamais. Trou type ERR-013.

## Tâche
1. Lire `agent_validation.replay_annuel` (L224+) pour connaître la FORME EXACTE de son retour.
2. Dans `brain_validation.py` : au moment d'assembler le rapport (main / build_output amont),
   appeler `av.replay_annuel()` SANS argument (c'est LA consultation du holdout profond :
   elle DOIT se consigner au registre — comportement voulu), en BEST-EFFORT ABSOLU
   (try/except -> pas de champ, rapport intact, jamais de crash), et FUSIONNER l'IC par
   agent dans les lignes de `ranking` : `row["annuel"] = {"ic": <ic de l'agent>}` (adapter
   à la forme réelle du retour ; ne fusionner que les agents présents dans le retour).
   Si build_output est le bon endroit, garder sa signature RÉTRO-COMPATIBLE (param optionnel).
3. Coût : cadence 6 h acceptable (cpcv_diagnostic tourne déjà sur le même panel profond).
   Si un partage de calcul simple avec cpcv_diagnostic est possible sans refactor lourd,
   fais-le ; sinon accepte le coût et documente-le.
4. Tests dans `tests_audit.py`, à insérer JUSTE AVANT `def _run_all():` :
   - fusion correcte depuis un retour `replay_annuel` SYNTHÉTIQUE injecté (monkeypatch de
     `agent_validation.replay_annuel` — AUCUN réseau, AUCUNE consultation du vrai holdout,
     ERR-019) : les lignes ranking reçoivent `annuel.ic`, et `edge_ladder._annuel_ok`
     bride bien un ic négatif / laisse passer un ic positif à travers le rapport fusionné ;
   - échec de replay_annuel (exception) -> rapport SANS champ annuel, aucun crash ;
   - docstrings en français, style des tests voisins.

## Contraintes globales (constitution)
- graphify D'ABORD pour t'orienter (`graphify query "..."`)
  avant grep/lecture — règle du dépôt.
- Ne touche PAS : parity_harness.py, lab_scenarios.py, edge_ladder.py, config.py,
  .claude/agents/*.md, guards/murs/kill-switch.
- Avant commit : `bash gates.sh` (3 portes vertes) puis `git add <fichiers> && git commit -m "..."`.
  Message de commit en FRANÇAIS, JAMAIS d'identifiant de modèle, JAMAIS de backticks ni de
  $() dans le message. NE PUSH PAS.
- `graphify update .` après tes modifications de code.
