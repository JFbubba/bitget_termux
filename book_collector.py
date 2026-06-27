"""
book_collector.py — collecteur HAUTE FIDÉLITÉ de microstructure via WebSocket public
Bitget. Classement : SAFE. Flux PUBLIC, lecture seule, AUCUNE clé, AUCUN ordre.

Upgrade du REST-poll de microstructure.py : se connecte à
`wss://ws.bitget.com/v2/ws/public` et s'abonne aux canaux `books15` (carnet L2, 15
niveaux, snapshots) + `trade` (tape). À cadence fixe, calcule les features et les écrit
dans le buffer roulant (microstructure.append_snapshot) que les agents T4 lisent.

Conception TESTABLE : le parsing et la mise à jour d'état sont des fonctions PURES
(`parse_ws_book`, `parse_ws_trades`, `handle_message`, `tick`) ; le câblage WebSocket
(run) est une couche fine. websocket-client est une dépendance OPTIONNELLE
(requirements-optional.txt) ; sans elle, le REST-poll de microstructure.py reste dispo.

HONNÊTETÉ : `books15` = snapshots L2 (pas l'incrémental par-événement complet `books`,
qui exige la gestion de checksum/resync — upgrade v2). Pas de L3 (indisponible public).
"""

import json
import time

WS_URL = "wss://ws.bitget.com/v2/ws/public"
DEFAULT_INST_TYPE = "USDT-FUTURES"
PING_EVERY = 25.0                 # Bitget ferme la connexion sans ping ~30 s


# ---------- parsing PUR ----------

def parse_ws_book(item):
    """Snapshot de carnet WS -> {bids, asks} flottants. Pur."""
    bids = [[float(p), float(s)] for p, s in (item.get("bids") or [])]
    asks = [[float(p), float(s)] for p, s in (item.get("asks") or [])]
    return {"bids": bids, "asks": asks}


def parse_ws_trades(data):
    """Tape WS -> [{side, size, price}]. Gère les formats objet ET tableau. Pur.
    Bitget v2 trade : objets {ts,price,size,side} ou tableaux [ts,price,size,side]."""
    out = []
    for t in data or []:
        if isinstance(t, dict):
            out.append({"side": str(t.get("side", "")).lower(),
                        "size": float(t.get("size", 0) or 0),
                        "price": float(t.get("price", 0) or 0)})
        elif isinstance(t, (list, tuple)) and len(t) >= 4:
            out.append({"side": str(t[3]).lower(), "size": float(t[2]), "price": float(t[1])})
    return out


def subscribe_message(symbols, inst_type=DEFAULT_INST_TYPE):
    """Message d'abonnement books15 + trade pour les symboles. Pur."""
    args = []
    for s in symbols:
        args.append({"instType": inst_type, "channel": "books15", "instId": s})
        args.append({"instType": inst_type, "channel": "trade", "instId": s})
    return json.dumps({"op": "subscribe", "args": args})


def handle_message(state, raw):
    """Met à jour l'état {books, trades} depuis un message WS brut. Pur (hors json).
    Ignore pong / acks d'abonnement / erreurs. Retourne l'état muté."""
    if not raw or raw == "pong":
        return state
    try:
        data = json.loads(raw)
    except Exception:
        return state
    if not isinstance(data, dict) or data.get("event"):
        return state                                    # ack/erreur d'abonnement
    arg = data.get("arg") or {}
    ch, inst = arg.get("channel"), arg.get("instId")
    d = data.get("data") or []
    if not inst or not d:
        return state
    if ch in ("books15", "books5", "books1", "books"):
        state.setdefault("books", {})[inst] = parse_ws_book(d[0])
    elif ch == "trade":
        state.setdefault("trades", {}).setdefault(inst, []).extend(parse_ws_trades(d))
    return state


def tick(state, symbols, ts=None):
    """Calcule les features depuis l'état courant -> buffer microstructure. Best-effort.
    Maintient le carnet précédent (pour l'OFI) et vide la tape accumulée. Retourne le
    nb de snapshots écrits."""
    import microstructure
    prev = state.setdefault("prev", {})
    written = 0
    for s in symbols:
        book = state.get("books", {}).get(s)
        if not book:
            continue
        trades = state.get("trades", {}).pop(s, [])
        snap = microstructure.features(prev.get(s), book, trades)
        snap["ts"] = int(ts if ts is not None else time.time())
        prev[s] = book
        microstructure.append_snapshot(s, snap)
        written += 1
    return written


# ---------- câblage WebSocket (couche fine, best-effort) ----------

def _rest_poll_fallback(symbols, cadence):
    """Repli BASSE FIDÉLITÉ si websocket-client est absent : poll REST round-robin via
    microstructure.collect_once. Le service reste UTILE (pas de crash-loop)."""
    import microstructure
    print("book_collector: 'websocket-client' absent -> repli REST-poll (basse fidélité). "
          "Pour la haute fidélité : sudo apt install -y python3-websocket (ou "
          "pip install --break-system-packages websocket-client), puis redémarrer le service.")
    while True:
        for s in symbols:
            microstructure.collect_once(s)
        time.sleep(max(1.0, cadence))


def run(symbols=("BTCUSDT",), inst_type=DEFAULT_INST_TYPE, cadence=1.0):
    """Boucle WebSocket : connecte, s'abonne, calcule les features à `cadence` (s).
    Si `websocket-client` est absent -> repli REST-poll (service jamais en crash-loop).
    Reconnexion automatique."""
    symbols = list(symbols)
    try:
        import websocket
    except Exception:
        _rest_poll_fallback(symbols, cadence)
        return
    import threading
    state = {}
    lock = threading.Lock()                             # protège l'état partagé WS<->worker

    def on_open(ws):
        ws.send(subscribe_message(symbols, inst_type))

    def on_message(ws, msg):
        with lock:                                      # mutation depuis le thread WS
            handle_message(state, msg)

    def worker(ws):
        last_ping = 0.0
        while True:
            time.sleep(max(0.5, cadence))
            now = time.time()
            try:
                if now - last_ping >= PING_EVERY:
                    ws.send("ping"); last_ping = now
                with lock:                              # lecture/pop cohérente de l'état
                    tick(state, symbols)
            except Exception:
                return                                  # socket mort -> run_forever relancera

    while True:
        ws = websocket.WebSocketApp(WS_URL, on_open=on_open, on_message=on_message)
        threading.Thread(target=worker, args=(ws,), daemon=True).start()
        try:
            ws.run_forever(ping_interval=0)
        except Exception:
            pass
        time.sleep(2.0)                                 # backoff avant reconnexion


def main():
    import sys
    syms = sys.argv[1:] or ["BTCUSDT"]
    print(f"=== COLLECTEUR MICROSTRUCTURE (WebSocket public Bitget) {syms} ===")
    print("Lecture seule, aucune clé, aucun ordre. Ctrl-C pour arrêter. VERDICT: SAFE")
    run(syms)


if __name__ == "__main__":
    main()
