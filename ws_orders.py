"""
ws_orders.py — écoute WS PRIVÉE du canal `orders` Bitget (futures USDT-M).

Classement : SAFE, LECTURE SEULE. Instrument d'OBSERVATION pur (SAVOIR §11 : la
confirmation temps réel des ordres/fills par le canal WS PRIVÉ `orders`
(BITGET_REFERENCE §8f) est LE chaînon manquant identifié face au polling actuel).
Étape 1 = mesure-d'abord : AUCUNE décision, AUCUN ordre, AUCUN branchement dans le
cerveau ou l'exécution. Ce module MESURE la latence et la complétude du canal —
rien n'est câblé à l'argent tant qu'une mesure ne le justifie pas.

Login WS signé avec la clé `.env` — RÉUTILISE `bitget_balance_reader.create_signature`
(même contrat HMAC-SHA256/Base64 que le REST signé, BITGET_REFERENCE §10a) : AUCUNE
nouvelle logique de signature. Le login WS Bitget v2 (`op":"login"`, preHash =
timestamp(secondes) + "GET" + "/user/verify") est le contrat PUBLIC documenté
(api-doc/common/websocket-intro, cf. BITGET_REFERENCE §5) — pas une invention de ce
module. AUCUN secret n'est jamais journalisé, affiché ou renvoyé par `--status`.

Forme des évènements du canal `orders` : BITGET_REFERENCE §8f ne documente que
l'EXISTENCE du canal (fills/statut temps réel), pas le schéma champ-à-champ exact.
`parse_order_event` est donc DÉLIBÉRÉMENT tolérant : plusieurs noms de champs
plausibles sont essayés (documentés en commentaire), un champ absent -> None dans
la ligne de journal (JAMAIS d'exception, JAMAIS de suppression silencieuse de
l'évènement). La complétude réelle du schéma est elle-même une donnée à mesurer
via `--status` (nb_avec_latence < nb_evenements = signal qu'un champ suppose à
tort est absent en pratique).

Résilience (SAVOIR §11.4) : reconnexion à backoff exponentiel + JITTER borné,
ping/pong (chaîne "ping", 30 s — §3/§10c), re-login après la déconnexion forcée
24 h (§10c, régime NORMAL, pas une panne). Épuisement des tentatives -> sortie
propre (le superviseur systemd, Restart=always, relance ; ce module n'installe
PAS son unité — décision de déploiement au contrôleur). Jamais de boucle chaude.

Journal append-only borné (JSONL, rotation via `journal_append`) :
{ts_event_exchange, ts_reception, latence_ms, type_evenement, symbol, order_id,
statut, side, taille, prix, fill}. PAS de clé, PAS de secret — seuls les montants
d'ordres (déjà visibles au propriétaire via l'API) sont journalisés.

CLI :
  python ws_orders.py --daemon      # boucle infinie (service systemd, jamais lancé ici)
  python ws_orders.py --once N      # connecte N secondes puis stop (test manuel)
  python ws_orders.py --status      # lecture seule du journal : agrégats

Dépendance : `websocket-client` (déjà listée en OPTIONNELLE, requirements-optional.txt ;
déjà installée sur cette machine, réutilisée par `book_collector.py`). Absente ->
message clair, AUCUN crash, sortie propre (rien à observer sans elle).
"""

import json
import os
import random
import time
from pathlib import Path

from config_utils import load_env as _load_env
from numeric_utils import safe_float
import journal_append

_load_env()

ROOT = Path(__file__).resolve().parent

WS_URL_PRIVATE = "wss://ws.bitget.com/v2/ws/private"
INST_TYPE = "USDT-FUTURES"
CHANNEL = "orders"
PING_EVERY = 25.0                    # Bitget ferme sans ping ~30 s (BITGET_REFERENCE §3/§10c)

JOURNAL = ROOT / ".ws_orders_journal.jsonl"
JOURNAL_MAX_BYTES = 20_000_000

BACKOFF_BASE_S = 1.0
BACKOFF_FACTOR = 2.0
BACKOFF_CAP_S = 60.0
MAX_RETRIES = 8                      # épuisement -> sortie propre (jamais de boucle chaude)
STABLE_CONN_S = 60.0                 # connexion vécue >= ce seuil -> on considère la reprise
                                      # SAINE et on remet le compteur de tentatives à 0 (sinon
                                      # une déco/reco normale toutes les 24h userait les
                                      # tentatives d'un service par ailleurs stable)


# ---------- fonctions PURES (signature/messages/parsing/backoff/agrégats) ----------

def _to_int_ts(v):
    """Timestamp WS (ms epoch Bitget) -> int. 0 si absent/illisible. PUR."""
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return 0


def login_message(api_key, secret, passphrase, ts_s=None):
    """Message JSON de login WS privé Bitget (`op":"login"`). Signature = même
    contrat HMAC-SHA256/Base64 que le REST signé (`bitget_balance_reader.create_signature`,
    BITGET_REFERENCE §10a) sur preHash = timestamp(SECONDES) + "GET" + "/user/verify"
    (pas de query, pas de body). PUR si `ts_s` est fourni (déterministe, testable sans
    horloge système — pas de secret dans la valeur retournée au-delà du sign attendu)."""
    from bitget_balance_reader import create_signature
    ts = str(int(ts_s if ts_s is not None else time.time()))
    sign = create_signature(secret, ts, "GET", "/user/verify")
    return json.dumps({"op": "login",
                        "args": [{"apiKey": api_key, "passphrase": passphrase,
                                  "timestamp": ts, "sign": sign}]})


def subscribe_message(inst_type=INST_TYPE, channel=CHANNEL, inst_id="default"):
    """Message d'abonnement au canal privé `orders` (futures USDT-M). PUR."""
    return json.dumps({"op": "subscribe",
                        "args": [{"instType": inst_type, "channel": channel, "instId": inst_id}]})


def parse_order_event(raw, ts_reception=None):
    """Évènement WS brut du canal privé `orders` -> liste de lignes de journal PURES
    (une par ordre/fill dans le message, généralement 1). Tolérant PAR CONSTRUCTION
    (schéma exact non documenté, cf. docstring module) : champ absent -> None dans la
    ligne, JAMAIS d'exception. Ignore les acks (`event`, ex. login/subscribe/erreur)
    et tout canal différent de `orders`. `raw` : str JSON ou dict déjà parsé (pour
    les tests, sans dépendre de json.dumps)."""
    ts_reception = int(ts_reception if ts_reception is not None else time.time() * 1000)
    if raw is None or raw in ("ping", "pong"):
        return []
    data = raw
    if isinstance(raw, str):
        try:
            data = json.loads(raw)
        except Exception:
            return []
    if not isinstance(data, dict):
        return []
    if data.get("event"):                       # ack login/subscribe, ou erreur -> pas un ordre
        return []
    arg = data.get("arg") or {}
    ch = arg.get("channel")
    if ch is not None and ch != CHANNEL:
        return []
    items = data.get("data") or []
    if not isinstance(items, list):
        return []
    msg_ts = _to_int_ts(data.get("ts"))
    out = []
    for it in items:
        if not isinstance(it, dict):
            continue
        # Champs de temps par-item essayés dans cet ordre (aucun n'est garanti par
        # BITGET_REFERENCE) : uTime/cTime/fillTime (conventions v2 REST recoupées) ->
        # repli sur le `ts` du message enveloppe.
        ts_evt = (_to_int_ts(it.get("uTime")) or _to_int_ts(it.get("cTime"))
                  or _to_int_ts(it.get("fillTime")) or msg_ts)
        latence_ms = (ts_reception - ts_evt) if ts_evt else None
        fill_prix = safe_float(it.get("fillPrice") if it.get("fillPrice") is not None
                                else it.get("priceAvg"))
        fill_taille = safe_float(it.get("baseVolume") if it.get("baseVolume") is not None
                                  else (it.get("fillSize") if it.get("fillSize") is not None
                                        else it.get("accBaseVolume")))
        fill = None
        if fill_prix is not None or fill_taille is not None or it.get("tradeId"):
            fill = {"prix": fill_prix, "taille": fill_taille, "trade_id": it.get("tradeId")}
        out.append({
            "ts_event_exchange": ts_evt or None,
            "ts_reception": ts_reception,
            "latence_ms": latence_ms,
            "type_evenement": data.get("action"),
            "symbol": it.get("instId"),
            "order_id": it.get("orderId"),
            "client_oid": it.get("clientOid"),
            "statut": it.get("status"),
            "side": it.get("side"),
            "taille": safe_float(it.get("size")),
            "prix": safe_float(it.get("price")),
            "fill": fill,
        })
    return out


def backoff_delay(attempt, base=BACKOFF_BASE_S, factor=BACKOFF_FACTOR, cap=BACKOFF_CAP_S, rng=None):
    """Délai (s) avant la reconnexion n°`attempt` (0-indexée). Backoff EXPONENTIEL
    borné par `cap`, plus un JITTER dans [0, 50% du délai borné] (SAVOIR §11.4,
    invariant 4). `rng` injectable : callable () -> valeur dans [0,1) (déterminisme
    test) ; sinon `random.random()`. PUR (hors horloge/aléa, tous deux injectables)."""
    exp = base * (factor ** max(0, int(attempt)))
    capped = min(exp, cap)
    r = rng() if rng is not None else random.random()
    r = max(0.0, min(1.0, r))
    return round(capped + capped * 0.5 * r, 3)


def compute_status(records):
    """Agrégats PURS depuis une liste de lignes de journal déjà chargées (dicts).
    AUCUN I/O. Nb d'évènements, latence médiane/p95 (ms, sur les latences connues
    seulement), dernier évènement."""
    lat = sorted(r["latence_ms"] for r in records
                 if isinstance(r, dict) and isinstance(r.get("latence_ms"), (int, float))
                 and not isinstance(r.get("latence_ms"), bool))
    n = len(lat)

    def _pct(p):
        if not n:
            return None
        idx = min(n - 1, int(round(p * (n - 1))))
        return lat[idx]

    return {
        "nb_evenements": len(records),
        "nb_avec_latence": n,
        "latence_mediane_ms": _pct(0.5),
        "latence_p95_ms": _pct(0.95),
        "dernier_evenement": records[-1] if records else None,
    }


# ---------- I/O journal (best-effort, jamais de crash ; chemin injectable ERR-019) ----------

def append_event(entry, path=None):
    """Écrit UNE ligne de journal (append-only borné, rotation par taille). Best-effort
    (`journal_append.append_jsonl`) — ne lève jamais."""
    p = path if path is not None else JOURNAL
    return journal_append.append_jsonl(p, entry, max_bytes=JOURNAL_MAX_BYTES)


def status(path=None):
    """Lecture SEULE du journal -> agrégats (voir `compute_status`). `{}`-like (tous
    champs à 0/None) si le journal est absent/illisible."""
    p = path if path is not None else JOURNAL
    return compute_status(journal_append.read_jsonl(p))


# ---------- câblage WebSocket (couche fine, best-effort, JAMAIS de crash) ----------

def _keys():
    """Clés `.env` — None si l'une manque (fail-safe : jamais d'exception propagée,
    jamais de valeur affichée)."""
    k = os.getenv("BITGET_API_KEY")
    s = os.getenv("BITGET_API_SECRET")
    p = os.getenv("BITGET_API_PASSPHRASE")
    if not k or not s or not p:
        return None
    return k, s, p


def run(duration_s=None, path=None):
    """Boucle WS privée `orders` : login signé, souscription, journal des évènements,
    reconnexion à backoff exponentiel+jitter (jamais de boucle chaude). `duration_s` :
    arrêt après N secondes (tests manuels, `--once`) ; None = boucle infinie (`--daemon`,
    le superviseur systemd relance après épuisement des tentatives). JAMAIS de crash :
    dépendance/clé indisponible ou erreur réseau -> message clair + sortie/retry, pas
    d'exception qui remonte."""
    try:
        import websocket
    except Exception:
        print("ws_orders: 'websocket-client' absent -> observation impossible ici "
              "(pip install --break-system-packages websocket-client). Sortie propre.")
        return
    keys = _keys()
    if keys is None:
        print("ws_orders: clés BITGET_API_KEY/BITGET_API_SECRET/BITGET_API_PASSPHRASE "
              "manquantes dans .env -> canal privé inaccessible. Sortie propre (rien à "
              "observer sans clé).")
        return
    api_key, secret, passphrase = keys
    import threading
    start = time.time()

    def on_open(ws):
        try:
            ws.send(login_message(api_key, secret, passphrase))
        except Exception:
            pass

    def on_message(ws, msg):
        if msg in ("ping", "pong"):
            return
        try:
            data = json.loads(msg)
        except Exception:
            return
        if isinstance(data, dict) and data.get("event") == "login":
            if str(data.get("code", "")) in ("0", "00000"):
                try:
                    ws.send(subscribe_message())
                except Exception:
                    pass
            return
        for entry in parse_order_event(data, ts_reception=int(time.time() * 1000)):
            append_event(entry, path=path)

    def worker(ws):
        last_ping = 0.0
        while True:
            time.sleep(1.0)
            now = time.time()
            if duration_s is not None and now - start >= duration_s:
                try:
                    ws.close()
                except Exception:
                    pass
                return
            if now - last_ping >= PING_EVERY:
                try:
                    ws.send("ping")
                    last_ping = now
                except Exception:
                    return                       # socket mort -> run_forever relancera

    attempt = 0
    while True:
        if duration_s is not None and time.time() - start >= duration_s:
            return
        conn_start = time.time()
        ws = websocket.WebSocketApp(WS_URL_PRIVATE, on_open=on_open, on_message=on_message)
        threading.Thread(target=worker, args=(ws,), daemon=True).start()
        try:
            ws.run_forever(ping_interval=0)
        except Exception:
            pass
        if duration_s is not None and time.time() - start >= duration_s:
            return
        if time.time() - conn_start >= STABLE_CONN_S:
            attempt = 0                          # connexion vécue assez longtemps -> repart neuf
        else:
            attempt += 1
        if attempt > MAX_RETRIES:
            print(f"ws_orders: {MAX_RETRIES} tentatives de reconnexion épuisées -> "
                  "sortie propre (le superviseur systemd relance). VERDICT: SAFE")
            return
        time.sleep(backoff_delay(attempt))


def main():
    import sys
    argv = sys.argv[1:]
    if "--status" in argv:
        s = status()
        print("=== ws_orders --status (lecture seule, aucun ordre) ===")
        print(f"Évènements journalisés : {s['nb_evenements']}")
        print(f"  dont latence connue  : {s['nb_avec_latence']}")
        print(f"Latence médiane (ms)   : {s['latence_mediane_ms']}")
        print(f"Latence p95 (ms)       : {s['latence_p95_ms']}")
        print(f"Dernier évènement      : {s['dernier_evenement']}")
        print("VERDICT: SAFE")
        return
    if "--once" in argv:
        idx = argv.index("--once")
        n = safe_float(argv[idx + 1] if idx + 1 < len(argv) else None, 30.0)
        print(f"=== ws_orders --once {n}s (observation, aucun ordre) ===")
        run(duration_s=n)
        print("Terminé. VERDICT: SAFE")
        return
    if "--daemon" in argv:
        print("=== ws_orders --daemon (WS privé `orders`, observation, aucun ordre) ===")
        run(duration_s=None)
        return
    print("Usage: python ws_orders.py [--daemon | --once N | --status]")
    print("SAFE — instrument d'observation pur (aucune décision, aucun ordre).")


if __name__ == "__main__":
    main()
