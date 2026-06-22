"""
dashboard/server.py — dashboard web LECTURE SEULE (stdlib uniquement).

Classement : SAFE.
  - sert un tableau de bord HTML + un endpoint JSON /api/state
  - agrège des données read-only (stats, order-flow Bitget, macro, santé)
  - aucun ordre, aucun secret, aucune écriture de trading

Dépendances : bibliothèque standard Python seulement (http.server).
Les modules data (bitget_market_data, macro_context...) sont importés
paresseusement et de façon défensive : le dashboard démarre même si une
source est indisponible.

Lancement :
    python dashboard/server.py
Config (env) :
    DASH_HOST (défaut 127.0.0.1)   DASH_PORT (défaut 8787)
    DASH_SYMBOL (défaut BTCUSDT)
Voir dashboard/DEPLOY.md pour le déploiement VPS (SSH tunnel / nginx + ufw).
"""

import json
import os
import sys
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs

STATIC_DIR = Path(__file__).resolve().parent
# La racine du repo (parent de dashboard/) doit être importable : les modules
# data (config, stats_report, ...) y vivent. Sinon `import config` échoue
# quand on lance `python dashboard/server.py`.
REPO_ROOT = STATIC_DIR.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
DEFAULT_SYMBOL = os.getenv("DASH_SYMBOL", "BTCUSDT")
HOST = os.getenv("DASH_HOST", "127.0.0.1")
PORT = int(os.getenv("DASH_PORT", "8787"))

_CACHE = {}


def _cached(key, ttl, producer):
    now = time.time()
    hit = _CACHE.get(key)
    if hit and now - hit[0] < ttl:
        return hit[1]
    value = producer()
    _CACHE[key] = (now, value)
    return value


def _safe(producer, default=None):
    try:
        return producer()
    except Exception:
        return default


def _count_csv(path):
    p = Path(path)
    if not p.exists():
        return 0
    with p.open("r", encoding="utf-8", errors="ignore") as f:
        return max(sum(1 for _ in f) - 1, 0)


def assemble_state(symbol, symbols, stats, orderflow, macro, health):
    """Assemble l'état du dashboard (fonction pure, testable)."""
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "mode": "PAPER / DRY-RUN",
        "symbol": symbol,
        "symbols": list(symbols or []),
        "stats": stats or {},
        "orderflow": orderflow,
        "macro": macro,
        "health": health or {},
    }


def build_state(symbol=None):
    symbol = symbol or DEFAULT_SYMBOL

    def _stats():
        import stats_report
        return stats_report.compute_stats(stats_report.load_rows())

    def _orderflow():
        import bitget_market_data
        return bitget_market_data.market_snapshot(symbol)

    def _macro():
        import macro_context
        return macro_context.macro_snapshot()

    def _health():
        import config
        return {
            "signals": _count_csv(config.SIGNALS_JOURNAL_FILE),
            "open_positions": _count_csv(config.OPEN_STATE_FILE),
            "finalized": _count_csv(config.FINAL_OUTCOMES_FILE),
        }

    def _symbols():
        import config
        return config.SYMBOLS

    stats = _safe(_stats, {})
    orderflow = _cached(f"of:{symbol}", 20, lambda: _safe(_orderflow, None))
    macro = _cached("macro", 300, lambda: _safe(_macro, None))
    health = _safe(_health, {})
    symbols = _safe(_symbols, [symbol])

    return assemble_state(symbol, symbols, stats, orderflow, macro, health)


class Handler(BaseHTTPRequestHandler):
    def _send(self, code, ctype, body):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path.rstrip("/") in ("", "/index.html") or parsed.path == "/":
            try:
                html = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
            except OSError:
                self._send(500, "text/plain; charset=utf-8", b"index.html introuvable")
                return
            self._send(200, "text/html; charset=utf-8", html.encode("utf-8"))
        elif parsed.path == "/api/state":
            qs = parse_qs(parsed.query)
            symbol = (qs.get("symbol", [DEFAULT_SYMBOL])[0] or DEFAULT_SYMBOL).upper()
            body = json.dumps(build_state(symbol)).encode("utf-8")
            self._send(200, "application/json; charset=utf-8", body)
        elif parsed.path == "/healthz":
            self._send(200, "text/plain; charset=utf-8", b"ok")
        else:
            self._send(404, "text/plain; charset=utf-8", b"not found")

    def log_message(self, *args):
        pass  # silencieux


def main():
    print(f"=== DASHBOARD (lecture seule) sur http://{HOST}:{PORT} ===")
    print("Mode: PAPER / DRY-RUN. Aucun ordre. VERDICT: SAFE")
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nArrêt du dashboard.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
