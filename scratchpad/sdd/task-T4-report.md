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

---

# T4 — correctifs post-revue (21/07/2026)

## Statut

DONE. 3 correctifs appliqués (1 important + 2 mineurs), 723/723 tests, 3 portes vertes
(`gates.sh`), commit unique (non poussé — voir le hash rendu à l'appelant).

## Correctif 1 (Important) — échec login/subscribe SILENCIEUX

Constat de la revue : `on_message` (ws_orders.py, boucle `run()`) ne traitait que
`event=="login"` réussi (code 0/00000). Un ack `event:"error"` (signature invalide,
horloge dérivée, passphrase fausse, subscribe refusé — BITGET_REFERENCE §10d) tombait
dans `parse_order_event`, qui l'ignore par construction ([] — c'est son contrat, testé
par `test_ws_orders_parse_ignore_acks_et_autres_canaux`, contrat INCHANGÉ) : aucune trace,
le daemon pouvait tourner en zombie indéfiniment avec 0 événement, indistinguable d'un
schéma de champs faux (le risque que la mesure `--status` (nb_avec_latence < nb_evenements)
est censée détecter).

Correctifs apportés :

- **Nouvelle fonction PURE `ws_error_event(data, ts_reception=None)`** (ws_orders.py,
  à côté de `parse_order_event`) : détecte un ack d'ÉCHEC — `event:"error"` (toujours un
  échec) OU `event:"login"` avec un code ≠ 0/00000 (login refusé, qui n'arrivait pas
  forcément via `event:"error"` selon la doc consultée) — et produit une ligne de journal
  `{type_evenement:"ws_error", ts_reception, code, msg}`. `None` si `data` n'est PAS un
  ack d'échec (succès, ou tout autre message). **Aucun secret** : seuls `code`/`msg` de
  l'ack sont retenus, jamais l'objet `args` d'origine (qui porterait apiKey/passphrase/sign
  en cas de login) ni le message de login lui-même — vérifié par test (une ligne fabriquée
  avec des champs `apiKey`/`sign`/`passphrase` en plus ne les fait PAS fuiter dans la ligne
  produite).
- **`on_message`** : un ack `event` in `("error", "login")` passe désormais par
  `ws_error_event` AVANT `parse_order_event`. Si c'est un échec : la ligne `ws_error` est
  journalisée (`append_event`) + imprimée (`print`), puis **la connexion est fermée**
  (`ws.close()`) — elle sera comptée vers `MAX_RETRIES` par la boucle de reconnexion. Si ce
  n'est pas un échec (login réussi), `login_ok=True` (nouvelle variable de closure,
  `nonlocal`) et le `subscribe_message()` est envoyé comme avant.
- **Boucle de reconnexion (`run()`)** : la constante `STABLE_CONN_S` (reset du compteur de
  tentatives après 60 s de connexion « stable », quel que soit le login) est **retirée** —
  elle masquait exactement le bug visé (une connexion peut rester ouverte longtemps tout en
  échouant en boucle au login/subscribe). Remplacée par : `attempt` se remet à 0
  **uniquement si `login_ok` est vrai** durant la connexion qui vient de se terminer
  (sinon `attempt += 1`). `login_ok` est réinitialisé à `False` à chaque nouvelle tentative
  de connexion.
- **`compute_status`/`status`/`--status`** : nouveaux champs `nb_ws_error` (compte des
  lignes `type_evenement=="ws_error"`, séparé de `nb_evenements` qui reste réservé aux
  évènements d'ORDRE réels — sinon la mesure de complétude de schéma existante,
  `nb_avec_latence` vs `nb_evenements`, serait polluée) et `dernier_ws_error` (dernière
  ligne d'échec, code+msg). `--status` les imprime (« Erreurs ws (ws_error) »,
  « Dernière erreur ws »).

Test ajouté : `test_ws_orders_ws_error_ack_journalise_sans_secret_et_compte_status` —
`ws_error_event` sur `event:"error"` et sur `event:"login"` à code de refus (deux lignes
`{type_evenement, ts_reception, code, msg}` exactes) ; `None` sur succès/ack neutre/`raw`
non-dict ; **aucun secret** ne fuit même si l'ack de test porte apiKey/sign/passphrase ;
journalisé puis relu via `status(path=...)` (chemin injecté, ERR-019) : `nb_ws_error==2`,
dernier code/msg corrects, `nb_evenements==0` (aucun évènement d'ordre) ; mélangé à un
véritable évènement d'ordre : chaque compteur reste dans SA colonne (`nb_evenements==1`,
`nb_ws_error==2`, sans mélange). Le test pré-existant
`test_ws_orders_status_agregats_sur_journal_synthetique_injecte` a été ajusté (2 nouvelles
clés attendues dans le dict agrégats, valeurs neutres `0`/`None` sur un journal sans
erreur) — seul changement à un test existant, mécanique (conséquence directe de l'ajout
de champs à `compute_status`), aucune assertion pré-existante affaiblie.

## Correctif 2 (Mineur) — chaîne réservée « VERDICT: SAFE »

`ws_orders.py` imprimait « VERDICT: SAFE » à 3 endroits (épuisement des tentatives de
reconnexion, `--status`, `--once`) — chaîne réservée au verdict de `security_agent.py`
(que `gates.sh` grep pour la porte 2/3). Retirée des 3 endroits, remplacée par une fin de
ligne neutre : « lecture seule, aucun ordre ». Test ajouté :
`test_ws_orders_pas_de_verdict_safe_reserve_a_security_agent` (source du module ne
contient plus la chaîne).

## Correctif 3 (Mineur) — défense en profondeur (`security_agent.FILES_TO_SCAN`)

`ws_orders.py` n'était pas scanné par `security_agent.FILES_TO_SCAN` (noté comme réserve
dans la 1re version de ce rapport). Ajouté en fin de liste (même format que les entrées
existantes, une chaîne de nom de fichier). Vérifié : `security_agent.scan_file_for_keywords
("ws_orders.py") == []` (aucun mot-clé dangereux dans le source, y compris après les
correctifs 1/2) et `python security_agent.py` rend toujours `VERDICT: SAFE` (ws_orders.py
apparaît « OK » dans le scan). Test ajouté : `test_ws_orders_couvert_par_security_agent_scan`
(sur le même modèle que `test_fee_rates_source_readonly`).

## Tests couvrants (noms, commande, sortie)

Commande d'isolement (les 10 tests ws_orders, avant la suite complète) :

```
python3 -c "
import tests_audit as ta
tests = [
    'test_ws_orders_login_message_reutilise_signature_sans_secret',
    'test_ws_orders_parse_evenement_synthetique_latence_et_fill',
    'test_ws_orders_parse_champs_manquants_ligne_partielle_jamais_crash',
    'test_ws_orders_parse_ignore_acks_et_autres_canaux',
    'test_ws_orders_replay_parse_sans_reseau',
    'test_ws_orders_status_agregats_sur_journal_synthetique_injecte',
    'test_ws_orders_backoff_croissant_et_borne',
    'test_ws_orders_ws_error_ack_journalise_sans_secret_et_compte_status',
    'test_ws_orders_pas_de_verdict_safe_reserve_a_security_agent',
    'test_ws_orders_couvert_par_security_agent_scan',
]
for name in tests:
    getattr(ta, name)(); print('OK', name)
"
```

Sortie : les 10 lignes `OK test_ws_orders_...` (aucun échec).

Puis suite complète :

```
python tests_audit.py 2>&1 | tail -20
```

Sortie (extrait) : les 10 tests `ws_orders` en `PASS`, puis `723/723 tests OK`.

Puis les 3 portes :

```
bash gates.sh
```

Sortie :
```
— porte 1/3 : tests_audit —
723/723 tests OK
— porte 2/3 : security_agent —
VERDICT: SAFE
— porte 3/3 : safe_push_check —
SAFE PUSH CHECK OK
=== 3 PORTES VERTES ===
```

## Fichiers touchés (chemins absolus)

- `/root/bitget_termux_repo/ws_orders.py` — correctifs 1 et 2 (fonction `ws_error_event`,
  `on_message`/boucle de reconnexion durcies, docstrings mis à jour, 3 occurrences
  « VERDICT: SAFE » retirées, constante `STABLE_CONN_S` retirée — remplacée par le
  critère `login_ok`)
- `/root/bitget_termux_repo/security_agent.py` — correctif 3 (`ws_orders.py` ajouté à
  `FILES_TO_SCAN`, une ligne)
- `/root/bitget_termux_repo/tests_audit.py` — 2 tests ajoutés
  (`test_ws_orders_ws_error_ack_journalise_sans_secret_et_compte_status`,
  `test_ws_orders_pas_de_verdict_safe_reserve_a_security_agent`,
  `test_ws_orders_couvert_par_security_agent_scan` — 3 en réalité) + 1 test existant
  ajusté (2 nouvelles clés attendues dans les agrégats `--status`)
- `/root/bitget_termux_repo/scratchpad/sdd/task-T4-report.md` — cette section

Rien d'autre touché : aucun des fichiers explicitement exclus
(`brain_validation.py`/`agent_validation.py`/`holdout_registry.py`/`edge_ladder.py`/
`config.py`/`parity_harness.py`/`lab_scenarios.py`) n'a été modifié. Les modifications
étrangères présentes dans l'arbre de travail au moment de la correction
(`docs/BACKLOG_RECHERCHE.md`, `docs/RESEARCH_NOTES.md`, `scratchpad/sdd/task-T2-report.md`,
`scratchpad/sdd/task-T2-brief.md`, `scratchpad/firm_7b_results.json`,
`scratchpad/test_wyckoff_standalone.py` — une AUTRE tâche en cours) sont restées
**volontairement exclues** du commit (git add ciblé, uniquement les 4 fichiers ci-dessus).

## Réserves

- Le critère de remise à 0 du compteur de tentatives est désormais « un login a réussi
  durant CETTE connexion » — si le login réussit systématiquement mais que le SUBSCRIBE
  échoue systématiquement ensuite (ex. mauvais `instType`/canal), `attempt` continuerait
  de se remettre à 0 à chaque cycle (pas d'épuisement `MAX_RETRIES`). Ce n'est plus
  SILENCIEUX pour autant : chaque échec de subscribe est désormais journalisé (`ws_error`)
  et imprimé, donc visible immédiatement via `--status` — mais ce n'est pas un DEUXIÈME
  compteur d'épuisement dédié au subscribe. Non traité ici (hors périmètre des 3
  correctifs demandés) ; à signaler si mesuré en usage réel.
- Le schéma exact des acks d'échec Bitget (`event:"error"` vs `event:"login"` à code de
  refus) reste, comme le schéma des évènements d'ordre (réserve déjà notée ci-dessus),
  une hypothèse construite à partir de BITGET_REFERENCE §10d (table de codes) et non
  observée en direct sur le canal (le service n'est toujours pas déployé) — `ws_error_event`
  couvre les deux formes plausibles pour ne dépendre d'aucune des deux exclusivement.
