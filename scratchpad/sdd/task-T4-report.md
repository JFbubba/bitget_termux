# T4 — ws_orders.py : rapport d'implémentation

## Statut

DONE. 720/720 tests, 3 portes vertes, commit `d1d5660` (non poussé).

## Ce qui a été lu avant de coder (graphify-first)

- `graphify query` sur : signature/login WS Bitget, `book_collector` (WS public existant,
  pattern reconnexion), `journal_append` (JSONL borné), `numeric_utils.safe_float`,
  `security_agent`/`safe_push_check` (classification + mots interdits).
- `docs/BITGET_REFERENCE.md` §3 (WebSocket, limites/canaux), §8f (WS PRIVÉS `orders` +
  `Plan-Order`, candidat actionnable — l'existence du canal est documentée, **pas** le
  schéma champ-à-champ des évènements), §10a (signature `ACCESS-SIGN`), §10c (contrat de
  survie WS : déconnexion forcée 24h = régime normal, ping = string `"ping"` 30s), §10d
  (table de codes d'erreur).
- `docs/SAVOIR.md` §11 (invariants Nautilus : 1 exchange=source de vérité, 2 machine à
  états ambigus, 3 write-ahead, 4 backoff exponentiel+jitter ; chaînon manquant = WS privé
  `orders`).

## Dépendance WS constatée dans l'env

`websocket-client` **1.7.0 est déjà installé** sur cette machine (`python3 -c "import
websocket"` → OK) et déjà listé dans `requirements-optional.txt` (utilisé par
`book_collector.py`). **Aucune dépendance nouvelle n'a été ajoutée** — pas de BLOCKED.
J'ai ajouté une ligne de commentaire dans `requirements-optional.txt` notant que
`ws_orders.py` réutilise cette dépendance déjà présente.

## Méthode de signature réutilisée (pas réinventée)

`bitget_balance_reader.create_signature(secret, timestamp, method, request_path,
query_string, body)` — même contrat que le REST signé (`ACCESS-SIGN =
Base64(HMAC_SHA256(secret, preHash))`, BITGET_REFERENCE §10a). Le login WS
(`ws_orders.login_message`) l'appelle avec `preHash = timestamp(SECONDES) + "GET" +
"/user/verify"` (pas de query, pas de body) — c'est le contrat PUBLIC documenté du login
WS Bitget v2 (référencé via le lien SDK mirror de BITGET_REFERENCE §5), pas une invention
de ce module. Testé : `test_ws_orders_login_message_reutilise_signature_sans_secret`
vérifie que le `sign` produit est identique à `create_signature(...)` appelé directement,
et que le secret **n'apparaît jamais en clair** dans le message JSON produit.

## Forme des évènements parsés — honnêteté sur ce qui est documenté vs supposé

BITGET_REFERENCE §8f documente **l'existence** du canal `orders` (fills/statut
temps-réel) mais **pas** le schéma champ-à-champ exact des messages. `ws_orders.py` code
donc `parse_order_event` de façon **délibérément tolérante** :

- champs essayés (conventions v2 REST recoupées, jamais garanties) : `instId`, `orderId`,
  `clientOid`, `status`, `side`, `size`, `price`, `uTime`/`cTime`/`fillTime` (temps, dans
  cet ordre de priorité), `fillPrice`/`priceAvg`, `baseVolume`/`fillSize`/`accBaseVolume`,
  `tradeId` ;
- un champ absent → `None` dans la ligne de journal, **jamais d'exception** ;
- un item de la liste `data` qui n'est pas un dict → ignoré silencieusement, les autres
  items du même message restent traités ;
- un message qui n'est ni un dict ni une str JSON valide → `[]`, jamais de crash ;
- ack (`event`: login/subscribe/erreur) et canal ≠ `orders` → `[]` (pas de faux ordre
  journalisé) ;
- **le contrôle réel de complétude du schéma est reporté à la mesure** : une fois le
  service lancé, `--status` rend `nb_avec_latence` vs `nb_evenements` — si les vrais
  messages Bitget utilisent des noms de champs différents de ceux essayés ici,
  `nb_avec_latence` restera à 0 et le signal sera visible (jamais une fausse certitude
  silencieuse). C'est cohérent avec le rôle « étape 1 = observation, mesure-d'abord » du
  module : je ne prétends pas connaître le schéma exact, je le mesure.

## Forme du journal (ligne par évènement)

```json
{"ts_event_exchange": 1000500, "ts_reception": 1000800, "latence_ms": 300,
 "type_evenement": "update", "symbol": "BTCUSDT", "order_id": "OID1",
 "client_oid": "COID1", "statut": "filled", "side": "buy", "taille": 0.01,
 "prix": 60000.0, "fill": {"prix": 60001.5, "taille": 0.01, "trade_id": "T1"}}
```

Aucune clé/secret/montant de compte au-delà des montants d'ordres (autorisés par le brief
— déjà visibles au propriétaire via l'API).

## Résilience (SAVOIR §11.4)

- `backoff_delay(attempt, base=1.0, factor=2.0, cap=60.0, rng=...)` : exponentiel borné
  par `cap`, plus jitter dans `[0, 50% du délai borné]`, `rng` injectable pour le test
  déterministe. Testé croissant (rng=0) et borné même au pire jitter (rng=1) —
  `test_ws_orders_backoff_croissant_et_borne`.
- `MAX_RETRIES=8` : épuisement → sortie propre (le superviseur systemd, `Restart=always`,
  relance) — jamais de boucle chaude.
- `STABLE_CONN_S=60.0` : si une connexion a vécu ≥60s avant de tomber, le compteur de
  tentatives est remis à 0 — sinon la déconnexion forcée 24h (régime NORMAL, §10c)
  finirait par épuiser les tentatives d'un service par ailleurs sain.
- Ping = string `"ping"` toutes les 25s (marge sous les 30s du contrat serveur).

## Ce que le module NE fait PAS (bornes respectées)

- Aucun code d'ordre (vérifié : aucun mot-clé de `DANGEROUS_KEYWORDS`/`safe_push_check`
  présent dans `ws_orders.py` — grep de contrôle explicite fait avant commit).
- Aucun branchement dans `swarm_brain`, `futures_executor`, `spot_executor`, ni aucun
  agent voix.
- N'a touché AUCUN des fichiers listés comme interdits par le brief
  (`brain_validation.py`, `agent_validation.py`, `parity_harness.py`, `lab_scenarios.py`,
  `edge_ladder.py`, `config.py`, `.claude/agents/*.md`).
- L'unité systemd `deploy/ws-orders.service` est créée mais **non installée** (pas de
  `systemctl enable/start`, pas d'ajout à `deploy/install_units.sh` — le nom
  `ws-orders.service`, sans préfixe `bitget-`, échappe d'ailleurs au glob
  `bitget-*.service` de ce script, donc un futur `install_units.sh` inchangé ne
  l'installerait pas non plus par accident).
- Pas de verrou `.env` créé : le "gate" est le déploiement lui-même (service non
  installé), symétrique à `book_collector.py` (WS public existant) qui suit le même
  principe.

## Tests (TDD sur les fonctions pures)

Insérés dans `tests_audit.py` juste avant `def _run_all():`, après
`test_annuel_echec_replay_annuel_pas_de_crash()` (lignes ~14250-14432) :

1. `test_ws_orders_login_message_reutilise_signature_sans_secret` — signature identique
   au contrat REST, secret jamais en clair, déterminisme via `ts_s`.
2. `test_ws_orders_parse_evenement_synthetique_latence_et_fill` — latence calculée,
   regroupement `fill`, cas sans fill → `fill=None` (jamais un dict vide).
3. `test_ws_orders_parse_champs_manquants_ligne_partielle_jamais_crash` — champs
   totalement absents → ligne partielle, item corrompu dans la liste → sauté sans casser
   les autres, `raw` non-dict/JSON invalide/`None` → `[]`.
4. `test_ws_orders_parse_ignore_acks_et_autres_canaux` — acks login/subscribe/erreur et
   canal ≠ `orders` → `[]`.
5. `test_ws_orders_replay_parse_sans_reseau` — **`socket.socket` explose pendant l'appel**
   ; `parse_order_event`/`compute_status`/`backoff_delay`/`append_event`/`status` ne
   déclenchent aucune exception réseau (preuve qu'aucune tentative n'a lieu en mode
   parse/replay).
6. `test_ws_orders_status_agregats_sur_journal_synthetique_injecte` — chemin de journal
   **injecté** (tempfile, ERR-019) : nb_evenements/nb_avec_latence/médiane/p95/dernier,
   journal absent → agrégats neutres sans exception.
7. `test_ws_orders_backoff_croissant_et_borne` — suite croissante (jitter neutralisé),
   plafond respecté au pire jitter, robustesse `attempt` négatif / `rng` hors `[0,1]`.

Résultat : les 7 tests passent isolément, puis `python tests_audit.py` → **720/720 tests
OK** (713 avant + 7 nouveaux).

## Auto-revue avant commit

- Grep de contrôle des `DANGEROUS_KEYWORDS`/mots interdits de `safe_push_check.sh` sur
  `ws_orders.py` : 0 hit (attention particulière au mot `transfer`, dont le préfixe
  français `transfert` matche déjà la regex — évité partout, y compris dans les
  commentaires).
- Vérifié manuellement (hors suite de tests) : chemin clés manquantes → message clair,
  pas de crash ; chemin `websocket-client` absent (simulé via `builtins.__import__`
  patché) → message clair, pas de crash ; `--status` sur journal vide → agrégats à
  `None`/0.
- `ws_orders.py` n'est PAS dans `security_agent.FILES_TO_SCAN` (comme `book_collector.py`,
  `learning_health.py`, `watchdog.py` : modules SAFE hors du périmètre d'exécution
  audité) — c'est cohérent avec sa classification lecture-seule/observation ; il reste
  néanmoins scanné par le grep repo-large de `safe_push_check.sh` (`git grep` sur
  `*.py`), qui est passé.
- `git status`/`git diff --stat` vérifiés avant `git add` : le dépôt contenait des
  modifications d'une AUTRE tâche en cours (T2 : `docs/BACKLOG_RECHERCHE.md`,
  `docs/RESEARCH_NOTES.md`, `scratchpad/sdd/task-T2-report.md`, `scratchpad/sdd
  /task-T2-brief.md`, `scratchpad/firm_7b_results.json`,
  `scratchpad/test_wyckoff_standalone.py`) — **volontairement exclues** du commit T4 via
  `git add` ciblé (uniquement `ws_orders.py`, `deploy/ws-orders.service`, `tests_audit.py`,
  `docs/VERDICTS.md`, `scratchpad/LABOS.md`, `requirements-optional.txt`).

## Fichiers créés/touchés (chemins absolus)

- `/root/bitget_termux_repo/ws_orders.py` (nouveau, ~330 lignes)
- `/root/bitget_termux_repo/deploy/ws-orders.service` (nouveau, non installé)
- `/root/bitget_termux_repo/tests_audit.py` (7 tests ajoutés, lignes ~14250-14432)
- `/root/bitget_termux_repo/docs/VERDICTS.md` (1 entrée, section « ÉVALUÉ — service/donnée
  jugé (sans mesure d'edge) »)
- `/root/bitget_termux_repo/scratchpad/LABOS.md` (1 entrée)
- `/root/bitget_termux_repo/requirements-optional.txt` (commentaire, pas de nouvelle
  dépendance)

## Réserves

- Le schéma exact des champs du canal WS privé `orders` reste une **hypothèse à valider
  empiriquement** (BITGET_REFERENCE §8f ne documente pas le détail champ-à-champ). Le
  design est volontairement tolérant pour que cette hypothèse soit falsifiable via
  `--status` sans jamais crasher : une fois le service lancé quelques heures (décision du
  contrôleur — service NON installé par cette tâche), comparer `nb_avec_latence` vs
  `nb_evenements` dira si les noms de champs supposés (`uTime`/`cTime`/`fillTime`,
  `fillPrice`/`baseVolume`, etc.) correspondent à la réalité, et le cas échéant ajuster le
  parseur avant tout futur câblage.
- Aucune mesure de latence réelle n'a encore été faite (le service n'est pas déployé) :
  ce livrable est l'INSTRUMENT, pas la mesure elle-même — cohérent avec « étape 1 »
  mesure-d'abord du brief.
- Le nom de fichier `ws-orders.service` (sans préfixe `bitget-`) suit littéralement la
  demande du brief ; à signaler si le contrôleur préfère l'aligner sur la convention
  `bitget-*` du reste de `deploy/` avant de l'installer (impact : le glob de
  `install_units.sh` ne le ramasserait alors plus automatiquement s'il était renommé sans
  mise à jour du script — actuellement les deux se combinent pour garantir qu'aucune
  installation n'est accidentelle).
