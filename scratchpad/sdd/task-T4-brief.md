# T4 — ws_orders.py : écoute WS PRIVÉE du canal `orders` (chaînon SAVOIR §11, OBSERVATIONNEL)

## Pourquoi
SAVOIR §11 (invariants Nautilus) identifie LE chaînon manquant du bot : la confirmation
temps réel des ordres/fills par le canal WS PRIVÉ `orders` de Bitget (BITGET_REFERENCE §8f)
à la place du polling. Étape 1 = INSTRUMENT D'OBSERVATION pur (mesure-d'abord) : AUCUNE
décision, AUCUN ordre, AUCUN branchement dans l'exécution — on mesure la latence et la
complétude du canal AVANT tout câblage.

## Tâche
1. Lis `docs/BITGET_REFERENCE.md` §8f (canal WS privé `orders`, login signé) et §10
   (déconnexion forcée 24 h, ping/pong) AVANT toute supposition d'API (règle du dépôt).
2. Module `ws_orders.py` (SAFE, classement en tête de fichier) :
   - connexion WS privée Bitget (login signé avec la clé .env — RÉUTILISE la méthode de
     signature existante du dépôt, cherche comment bitget_execute/bitget_hub_bridge signent ;
     ne réinvente pas, n'affiche JAMAIS un secret) ;
   - souscription au canal `orders` (futures USDT-M) ;
   - chaque événement -> append JSONL borné (`.ws_orders_journal.jsonl`, rotation par taille
     comme journal_append si un utilitaire existe) avec {ts_event_exchange, ts_reception,
     latence_ms, type d'événement, symbol, orderId, statut, fill éventuel} — PAS de données
     de clé, PAS de montants secrets (les montants d'ordres sont OK) ;
   - résilience : reconnexion backoff exponentiel + JITTER (SAVOIR §11.4), ping/pong,
     re-login après la coupure 24 h ; épuisement des retries -> sortie propre (le superviseur
     relance), JAMAIS de boucle chaude ;
   - CLI : `--daemon` (boucle), `--once N` (N secondes puis stop, pour tests manuels),
     `--status` (lecture seule du journal : nb événements, latence médiane/p95, dernier événement).
3. Dépendance WS : vérifie ce qui est DÉJÀ installé dans l'env système (websocket-client ?
   websockets ? aiohttp ?). Si RIEN n'est disponible : STATUT BLOCKED avec le constat —
   n'installe RIEN toi-même (décision d'ajout de dépendance = contrôleur).
4. Unité systemd (fichier `deploy/ws-orders.service` sur le modèle des services existants,
   Restart=always) — NE L'INSTALLE PAS (le contrôleur décide du déploiement).
5. Tests avant `def _run_all():` dans tests_audit.py (offline, ERR-019 : chemins injectés) :
   - parsing d'un événement `orders` synthétique -> ligne de journal correcte (latence calculée) ;
   - le module en mode replay/parse n'appelle JAMAIS le réseau dans les tests ;
   - `--status` sur un journal synthétique injecté rend les bons agrégats ;
   - backoff : la suite des délais croît et est bornée (fonction pure testée).

## Contraintes globales (constitution)
- graphify d'abord (`graphify query "..."`), puis lecture ciblée.
- AUCUN code d'ordre (safe_push_check l'interdit hors modules autorisés) : ce module OBSERVE.
- Clé .env jamais dans un log/commit/message. `.ws_orders_journal.jsonl` -> .gitignore.
- Ne touche PAS : brain_validation.py, agent_validation.py, parity_harness.py, lab_scenarios.py,
  edge_ladder.py, config.py, .claude/agents/*.md.
- Avant commit : `bash gates.sh` vert puis commit en FRANÇAIS (jamais d'ID modèle, jamais de
  backticks ni $() dans le message). NE PUSH PAS. `graphify update .` après le code.
