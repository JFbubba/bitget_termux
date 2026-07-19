"""
tape_store.py — PERSISTANCE bornée de la TAPE brute signée (trades tick-level).

Classement : SAFE. Écrit/lit des fichiers LOCAUX seulement. AUCUN réseau, AUCUNE clé,
AUCUN ordre, AUCUN code d'exécution. Dépendances : stdlib pure (ERR-004 : aucun venv).

Pourquoi : `book_collector.tick()` reçoit la tape signée par trade puis la VIDE après
agrégation (magnitude buy/sell perdue) ; seuls des snapshots agrégés 60 s survivent. Il
n'existait donc AUCUNE tape tick-level historique — d'où le repli BVC-barre du labo VPIN
au lieu d'un vrai VPIN signé tick-level. Ce module APPEND la tape brute avant qu'elle soit
jetée, sous un plafond disque DUR, pour donner un socle de vérité aux recherches
microstructure/exécution (et au re-test VPIN tick-level).

Bornage disque (impératif, machine de prod) : rotation par TAILLE, par symbole.
  au plus (TAPE_KEEP + 1) fichiers × TAPE_MAX_MB par symbole.
  Défauts : 50 Mo × (4 rotations + 1 vif) = 250 Mo/symbole.
  Collecteur par défaut = 1 symbole (BTCUSDT) -> ~250 Mo ; 3 symboles -> ~750 Mo max.
Garde d'espace libre : sous TAPE_MIN_FREE_MB (défaut 500), on s'ABSTIENT (skip + log).

FAIL-SAFE ABSOLU : toute erreur (mkdir/rotation/disque/écriture) est attrapée -> on skip,
on log (throttlé), on continue. La persistance ne doit JAMAIS faire planter ni ralentir le
collecteur — la collecte de book/microstructure prime.

Gating : env `TAPE_PERSIST` (défaut ON — le but EST de collecter, mais borné ; =0 coupe).
"""

import json
import shutil
import time
from pathlib import Path

from config_utils import env_flag, env_num

_MB = 1024 * 1024
_ROOT = Path(__file__).resolve().parent

# Répertoire dédié, GITIGNORÉ. Variable de module -> injectable en test (comme
# microstructure.BUFFER_FILE l'est déjà dans la suite d'audit).
TAPE_DIR = _ROOT / ".tape"

_LAST_SKIP_LOG = {}                  # throttle des logs de skip par symbole (pas de spam)
_SKIP_LOG_EVERY_S = 300.0


# ---------- réglages (env-first, défauts en dur -> jamais de crash) ----------

def enabled():
    """Persistance active ? env `TAPE_PERSIST`, défaut ON (collecteur market-data SAFE)."""
    return env_flag("TAPE_PERSIST", True)


def _max_bytes():
    """Seuil de rotation par fichier (octets). Défaut 50 Mo. Plancher 1 octet (tests)."""
    mb = float(env_num("TAPE_MAX_MB", 50.0))
    return max(1, int(mb * _MB))


def _keep():
    """Nb de rotations conservées par symbole (.1 .. .N). Défaut 4. >=0."""
    return max(0, int(env_num("TAPE_KEEP", 4)))


def _min_free_bytes():
    """Plancher d'espace libre sous lequel on s'abstient (octets). Défaut 500 Mo."""
    mb = float(env_num("TAPE_MIN_FREE_MB", 500.0))
    return max(0, int(mb * _MB))


# ---------- chemins ----------

def _path(symbol):
    """Fichier vif de la tape d'un symbole."""
    return TAPE_DIR / f"{str(symbol).upper()}.jsonl"


def _rot(path, i):
    """Nom d'une rotation i (concat explicite -> pas de piège Path.with_suffix)."""
    return Path(str(path) + f".{i}")


# ---------- gardes ----------

def _enough_disk(target_dir):
    """Espace libre >= plancher ? En cas d'incertitude (stat impossible), on n'abstient
    PAS : le cap de TAILLE borne déjà l'empreinte, et fail-safe = ne pas bloquer."""
    try:
        return shutil.disk_usage(str(target_dir)).free >= _min_free_bytes()
    except Exception:
        return True


def _log_skip(symbol, reason):
    """Log de skip THROTTLÉ (jamais de spam, jamais d'exception)."""
    try:
        now = time.time()
        if now - float(_LAST_SKIP_LOG.get(symbol, 0.0)) < _SKIP_LOG_EVERY_S:
            return
        _LAST_SKIP_LOG[symbol] = now
        print(f"tape_store: persistance SKIP {symbol} ({reason}) — collecte poursuivie")
    except Exception:
        pass


# ---------- rotation ----------

def _rotate(path):
    """Fait tourner les fichiers : .N supprimé, .i -> .i+1, vif -> .1. keep=0 -> tronque.
    Best-effort, ne lève JAMAIS (appelé sous le try de persist, mais gardé ici aussi)."""
    keep = _keep()
    try:
        if keep <= 0:
            if path.exists():
                path.unlink()
            return
        oldest = _rot(path, keep)
        if oldest.exists():
            oldest.unlink()
        for i in range(keep - 1, 0, -1):
            src = _rot(path, i)
            if src.exists():
                src.rename(_rot(path, i + 1))
        if path.exists():
            path.rename(_rot(path, 1))
    except Exception:
        pass


# ---------- écriture (le hook additif du collecteur) ----------

def persist(symbol, trades, ts=None):
    """APPEND la tape brute signée d'un symbole (JSONL, 1 ligne/trade) avec rotation bornée.

    `trades` : liste de dicts {side, size, price} (+ `ts` par trade si dispo). FAIL-SAFE
    ABSOLU : toute erreur -> skip + log throttlé, retourne 0, ne lève JAMAIS. Retourne le
    nombre de lignes écrites (0 si désactivé / vide / skip disque / erreur)."""
    if not trades or not enabled():
        return 0
    sym = str(symbol).upper()
    try:
        TAPE_DIR.mkdir(parents=True, exist_ok=True)
        if not _enough_disk(TAPE_DIR):
            _log_skip(sym, "disque bas")
            return 0
        path = _path(sym)
        try:                                          # rotation AVANT écriture si trop gros
            if path.exists() and path.stat().st_size >= _max_bytes():
                _rotate(path)
        except Exception:
            pass
        now = int(ts if ts is not None else time.time())
        lines = []
        for t in trades:
            try:
                rec = {
                    "ts": int(t.get("ts", now) or now),
                    "symbol": sym,
                    "side": str(t.get("side", "")),
                    "size": float(t.get("size", 0.0) or 0.0),
                    "price": float(t.get("price", 0.0) or 0.0),
                }
            except Exception:
                continue                              # une ligne pourrie ne casse pas le lot
            lines.append(json.dumps(rec, ensure_ascii=False))
        if not lines:
            return 0
        with open(path, "a", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
        return len(lines)
    except Exception:
        _log_skip(sym, "erreur écriture")
        return 0


# ---------- lecture (l'API que consomment les labos : vpin tick-level, orderflow) ----------

def load_tape(symbol, since_ts=None, limit=None):
    """Relit la tape persistée d'un symbole (LECTURE SEULE). Concatène les rotations du
    plus ancien au plus récent (.keep .. .1) puis le fichier vif -> ordre chronologique.
    `since_ts` : ne garde que les trades de ts >= since_ts. `limit` : borne aux N derniers.
    Best-effort : renvoie [] si rien / erreur, ne lève JAMAIS."""
    sym = str(symbol).upper()
    out = []
    try:
        path = _path(sym)
        keep = _keep()
        files = [_rot(path, i) for i in range(keep, 0, -1)] + [path]
        for fp in files:
            try:
                if not fp.exists():
                    continue
                for line in fp.read_text(encoding="utf-8").splitlines():
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        rec = json.loads(line)
                    except Exception:
                        continue
                    if since_ts is not None:
                        try:
                            if float(rec.get("ts", 0) or 0) < float(since_ts):
                                continue
                        except Exception:
                            continue
                    out.append(rec)
            except Exception:
                continue
    except Exception:
        pass
    if limit:
        try:
            return out[-int(limit):]
        except Exception:
            return out
    return out


def stats(symbol):
    """Diagnostic LECTURE SEULE : présence/taille des fichiers de tape d'un symbole.
    Ne lève JAMAIS. {files: [...], total_bytes, keep, max_bytes}."""
    sym = str(symbol).upper()
    info = {"symbol": sym, "files": [], "total_bytes": 0,
            "keep": _keep(), "max_bytes": _max_bytes(), "enabled": enabled()}
    try:
        path = _path(sym)
        for fp in [path] + [_rot(path, i) for i in range(1, _keep() + 1)]:
            try:
                if fp.exists():
                    sz = fp.stat().st_size
                    info["files"].append({"name": fp.name, "bytes": sz})
                    info["total_bytes"] += sz
            except Exception:
                continue
    except Exception:
        pass
    return info


def main():
    """CLI diagnostic (lecture seule) : `python tape_store.py [SYMBOL]`."""
    import sys
    sym = (sys.argv[1] if len(sys.argv) > 1 else "BTCUSDT").upper()
    st = stats(sym)
    n = len(load_tape(sym, limit=5))
    print(f"=== TAPE STORE (persistance bornée, SAFE, lecture seule ici) {sym} ===")
    print(f"actif={st['enabled']} keep={st['keep']} max/fichier={st['max_bytes']//_MB or st['max_bytes']} "
          f"fichiers={len(st['files'])} total={st['total_bytes']} o")
    for f in st["files"]:
        print(f"  - {f['name']}: {f['bytes']} o")
    print(f"load_tape derniers échantillons lus: {n}")
    print("VERDICT: SAFE")


if __name__ == "__main__":
    main()
