# T6 — panneau « Validation & Parité » (dashboard, lecture seule) : rapport d'implémentation

## Statut

DONE. 726/726 tests, 3 portes vertes (`gates.sh`), commit `a287dbe` (non poussé).

## Ce qui a été lu avant de coder (graphify-first)

- `graphify query` sur : `validation_report.json`/ranking/annuel/ic par agent, `holdout_registry`
  (statut/consultations/contamine), `edge_ladder` (`build_report`/CPCV/annuel/ranking),
  `geometric_agent.systemic_risk_scale`, dashboard `server.py` (`_cached`/`_safe`/`build_state`/
  panneau kelly_dir).
- Lecture directe ensuite : `holdout_registry.py` (registre §mode recherche/gate_auto,
  `contamine` = >1 consultation "recherche" pour la MÊME version), `parity_harness.py`
  (`_dossier`, `_status`, format de session `{schema, symbol, ts, commit, rejeux:[...]}`,
  verdict `{ts, parite, divergences, frontieres_manquantes}`), `edge_ladder.py` (structure
  exacte de `row["annuel"]["ic"]`, `rep["cpcv"]["agents"][agent]` avec
  `ic_p10`/`frac_neg`/`n_chemins`/`gate_armee`), `geometric_agent.systemic_risk_scale` (fail-open
  absolu, `{scale, systemic_z, regime, n_hist, note}`), `config_utils.env_flag` (env-first,
  parsing strict).
- Confirmé sur le rapport RÉEL du dépôt (`validation_report.json`) que les clés supposées
  (`ranking[].annuel.ic`, `cpcv.agents[agent].{ic_p10,frac_neg,n_chemins}`, `cpcv.gate_armee`)
  correspondent bien à la production, pas seulement à la docstring.

## Design serveur

`dashboard/server.py` : fonction **module-level** `build_validation_gates(report=None,
holdout_chemin=None, parity_dossier=None, geom_fn=None)`, placée juste après `edge_summary`
(même convention « fonction pure, testable » — PAS un closure imbriqué dans `build_state`
comme l'esquisse initiale, précisément pour rester injectable en test sans dépendre du
réseau/disque de production). Sources toutes optionnelles/injectables (ERR-019) :

1. `annuel` : `{agent: ic_annuel_ou_None}` depuis `rep["ranking"]`.
2. `cpcv` : `{"gate_armee": bool, "agents": {agent: {ic_p10, frac_neg, n_chemins}}}` depuis
   `rep["cpcv"]`.
3. `holdout` : `holdout_registry.statut(holdout_chemin)` → liste triée par fraîcheur
   décroissante, 5 dernières, `{quoi, version, consultations, par_mode, contamine,
   dernier_ts}` (le champ `dernier_ts` est un ajout au-delà du strict minimum demandé — sert
   de fraîcheur affichable, donnée réelle de la source, jamais inventée).
4. `parite` : réutilise `parity_harness._dossier(parity_dossier)` pour la localisation (pas de
   duplication de la config de chemin) ; le glob+tri par mtime réplique nécessairement la
   logique de `_status()` car celle-ci IMPRIME sur stdout et ne renvoie pas de structure —
   rien d'utile à en importer directement au-delà de `_dossier`. Rend
   `{"paires": [{symbol, parite, ts, n_divergences}], "ok": x, "total": y}`.
5. `geometric_sizing` : `{"arme": env_flag("GEOMETRIC_RISK_SIZING"), "scale", "systemic_z",
   "regime"}` — **calculé qu'il soit armé ou non** (philosophie « mesure-d'abord » du
   `.env` : observer `systemic_z` avant d'armer). L'appel à `geometric_agent.systemic_risk_scale()`
   passe par un `_cached("geom_sizing_scale", 600, ...)` **dédié**, plus long que le TTL 300 s
   de la clé englobante, car ce calcul peut retomber sur du réseau (`portfolio_structure`).

Le tout est enveloppé `_safe()` sous-clé par sous-clé (une source qui casse ne fait tomber que
SA sous-clé, jamais tout le panneau) puis `state["validation_gates"] =
_cached("validation_gates", 300, lambda: _safe(build_validation_gates, {}))`, et ajouté au
bloc `_prewarm([...])` existant (parallélisé avec les autres producteurs indépendants,
juste après `"adl"`).

## Design front (`dashboard/index.html`)

Panneau `.panel` ajouté dans la grille `.bottom` (3 colonnes), juste avant « Recherche &
Labos », suivant le style établi (`.row`/`.k` pour les lignes scalaires, `.ic-h`/`.ic-r`
— grid 4 colonnes déjà utilisée par le panneau IC honnête — réutilisée telle quelle pour la
mini-table agent/IC-annuel/CPCV-p10/frac_neg). Fonction `renderValidationGates(vg)` :

- ligne parité : bilan `x/y paires en parité` (vert si toutes, rouge + compte de ✗ sinon),
  puis liste par paire (vert « PARITÉ OK », rouge « DIVERGENCE ✗ (n champs) », gris
  « jamais rejouée » si session jamais rejouée) ;
- ligne holdout : badge global (rouge « ⚠ CONTAMINÉ » si une entrée l'est, vert sinon, gris si
  aucun usage consigné) puis détail par (quoi, version) — rouge + ⚠ si contaminé ;
- mini-table agents : IC annuel (vert/rouge selon signe, gris si absent) + CPCV p10/frac_neg
  (rouge SEULEMENT si `gate_armee` ET (p10≤0 OU frac_neg>0.10), gris sinon — la porte CPCV
  desarmée ne colore jamais en rouge, cohérent avec `edge_ladder._cpcv_ok` fail-open) ;
- ligne géométrique : « OFF (défaut — mesure-d'abord) » + z observé si dispo quand désarmé,
  « ARMÉ · scale · z · régime » sinon (jaune si `scale<1`, vert sinon).

Chaque bloc dégrade en `—`/texte explicite si la sous-clé est vide (jamais de chiffre
inventé) ; le panneau entier est appelé dans `renderState()` via `try{
renderValidationGates(st.validation_gates||{}); }catch(e){}`, comme tous les autres panneaux
(erreur JS isolée ne casse jamais le reste du rendu).

## Tests (insérés juste avant `def _run_all():`)

1. `test_dashboard_validation_gates_structure_synthetique` — rapport synthétique
   (`ranking`/`cpcv`), dossier de parité **tmp** avec 2 sessions (1 divergence, 1 parité),
   registre holdout **tmp** avec 2 consultations "recherche" + 1 "gate_auto" (→ contaminé),
   `geom_fn` injecté. Vérifie la structure EXACTE des 5 sous-clés. `GEOMETRIC_RISK_SIZING`
   sauvegardé/forcé à `"0"`/restauré (comme `test_notional_systemic_gate_off_by_default_reduces_when_armed_b2`)
   — **ce VPS a réellement ce verrou armé dans son `.env`** (`GEOMETRIC_RISK_SIZING=1`,
   chargé par `config_utils.load_env()` à l'import de `config`) : sans ce contrôle explicite
   d'environnement le test était non-déterministe (a échoué une première fois en conditions
   réelles avant correction).
2. `test_dashboard_validation_gates_sources_absentes_fail_safe` — rapport `{}`, chemin
   holdout inexistant, dossier de parité inexistant **mais situé dans un tmp** (attention :
   `parity_harness._dossier()` fait un `mkdir(parents=True, exist_ok=True)` sur le chemin
   reçu — lui donner un chemin hors tmp aurait réellement créé un dossier en dehors du bac à
   sable du test), `geom_fn` qui lève une exception → chaque sous-clé retombe {}/[]/None,
   aucune exception ne remonte. Couvre aussi le chemin par défaut (`report=None`) avec
   `REPO_ROOT` monkeypatché vers un tmp sans `validation_report.json`.

Résultat : les 2 tests passent isolément, puis `python tests_audit.py` → **726/726 tests
OK** (724 avant + 2 nouveaux).

## Fichiers touchés (chemins absolus)

- `/root/bitget_termux_repo/dashboard/server.py` — fonction module-level
  `build_validation_gates` (après `edge_summary`), entrée dans `_prewarm([...])`, assignation
  `state["validation_gates"]`.
- `/root/bitget_termux_repo/dashboard/index.html` — panneau HTML « Validation & Parité »
  (grille `.bottom`), fonction JS `renderValidationGates`, appel dans `renderState()`.
- `/root/bitget_termux_repo/tests_audit.py` — 2 tests ajoutés juste avant `_run_all()`.
- `/root/bitget_termux_repo/scratchpad/sdd/task-T6-report.md` — ce rapport.

Aucun autre fichier touché (conformément à la consigne : uniquement `dashboard/server.py`,
le front du dashboard, et `tests_audit.py`).

## Réserves

- Le champ `dernier_ts` dans `holdout` est un ajout au-delà du strict `{quoi, version,
  consultations, par_mode, contamine}` demandé — inclus pour porter la fraîcheur réelle
  (donnée de la source, pas inventée) ; à retirer si le contrôleur préfère coller au strict
  minimum de la spec.
- `parity_harness._status()` étant un IMPRIMEUR (stdout, pas de structure retournée), le
  glob+tri par mtime dans `build_validation_gates` réplique nécessairement sa logique plutôt
  que de la « réutiliser » au sens strict — seul `_dossier()` (localisation du chemin,
  y compris override `PARITY_DIR`/injection test) est effectivement importé et appelé, ce qui
  est le seul point de réutilisation possible sans modifier `parity_harness.py` (hors
  périmètre autorisé de cette tâche).
- Le panneau geometric_sizing calcule `systemic_risk_scale()` (potentiellement réseau via
  `portfolio_structure`) MÊME quand `GEOMETRIC_RISK_SIZING` est désarmé, pour honorer la
  philosophie « mesure-d'abord » documentée dans `.env` — ce coût réseau supplémentaire est
  amorti par un cache dédié de 600 s (distinct du TTL 300 s de la clé englobante) et reste
  best-effort (fail-open à `None`/`1.0` selon la fonction source).
- N'a pas été vérifié en conditions de service réel (dashboard non redémarré/rechargé dans
  cette tâche) — vérifié uniquement via import direct du module (`spec_from_file_location`,
  comme tous les tests dashboard existants) et lecture visuelle du JS (syntaxe validée via
  `node --check` sur le bloc `<script>` extrait).
