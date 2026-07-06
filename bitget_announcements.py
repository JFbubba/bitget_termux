"""bitget_announcements.py — agent RISQUE « annonces Bitget » (idée du repo Bitget/radar).

Classement : SAFE (lecture seule, AUCUN ordre). Récupère les annonces publiques Bitget
(listings, delistings, suspensions, maintenances) et les score par un barème DÉTERMINISTE
(pas de LLM dans ce chemin — le garde-fou doit rester fiable même sans backend LLM).

Rôle : VÉTO SOUPLE à l'ouverture futures — on n'ouvre pas de position sur un symbole frappé
d'une annonce à fort impact (delisting/suspension), ce qui évite un risque RÉEL (position
qu'on ne pourrait plus fermer / force-close par l'exchange).

FAIL-OPEN volontaire : si l'API annonces est injoignable, AUCUN véto — une panne du flux
d'annonces ne doit pas HALTER le trading (c'est un overlay protecteur, pas une garde dure
comme les caps/kill-switch). Best-effort, caché (runtime_cache).
"""
from __future__ import annotations

import re

from config_utils import cfg as _cfg

# Barème d'impact DÉTERMINISTE 0..100 (inspiré de Bitget/scoring/impact_score.py).
BASE = {"delisting": 80, "suspension": 75, "maintenance": 45, "listing": 30, "other": 10}
KW = [("emergency", 15), ("exploit", 15), ("hack", 15), ("halt", 12), ("suspen", 12),
      ("delist", 12), ("withdraw", 10), ("deposit", 6), ("futures", 5), ("testnet", -25)]


def score_announcement(ann):
    """PUR. Score d'impact 0..100 d'une annonce {title, type}. Type inconnu -> 'other'."""
    if not isinstance(ann, dict):
        return 0
    base = BASE.get(str(ann.get("type", "other")).lower(), BASE["other"])
    title = str(ann.get("title", "")).lower()
    adj = sum(w for k, w in KW if k in title)
    return max(0, min(100, base + adj))


def classify(title):
    """PUR. Devine le type d'annonce depuis le titre (en_US)."""
    t = (title or "").lower()
    if any(k in t for k in ("delist", "will remove", "will no longer")):
        return "delisting"
    if any(k in t for k in ("suspen", "halt", "pause trading")):
        return "suspension"
    if "maintenance" in t or "system upgrade" in t:
        return "maintenance"
    if "list" in t:
        return "listing"
    return "other"


def symbols_in(title):
    """PUR. Extrait les symboles USDT cités dans un titre (heuristique). {'XRPUSDT', ...}."""
    t = (title or "").upper()
    out = set()
    for m in re.findall(r"\b([A-Z0-9]{2,15})(?:USDT|/USDT|-USDT)\b", t):
        out.add(m + "USDT")
    for m in re.findall(r"[(\$]([A-Z0-9]{2,10})[)\s]", t):   # tickers entre parenthèses / après $
        out.add(m + "USDT")
    return out


def _fetch():
    """Annonces Bitget publiques (best-effort). [] si tout échoue."""
    import json
    import urllib.request
    anns = []
    timeout = float(_cfg("ANNOUNCE_TIMEOUT_S", 6))
    for atype in ("coin_listings", "symbol_delisting", "maintenance", "api_bulletin"):
        u = ("https://api.bitget.com/api/v2/public/annoucements"   # faute = celle de l'API Bitget
             f"?language=en_US&annType={atype}")
        try:
            req = urllib.request.Request(u, headers={"User-Agent": "bitget-bot/1.0"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                d = json.loads(r.read().decode())
            for a in (d.get("data") or [])[:50]:
                title = a.get("annTitle") or a.get("title") or ""
                anns.append({"title": title, "type": classify(title), "ts": a.get("cTime")})
        except Exception:
            continue
    return anns


def fetch_announcements():
    """Annonces Bitget, caché (runtime_cache, TTL ANNOUNCE_TTL_S). [] si injoignable (FAIL-OPEN)."""
    try:
        import runtime_cache as rc
        return rc.get("bitget_announcements", int(_cfg("ANNOUNCE_TTL_S", 1800)), _fetch, fallback=[]) or []
    except Exception:
        try:
            return _fetch()
        except Exception:
            return []


def symbol_risk(symbol):
    """Score d'impact MAX (0..100) des annonces visant ce symbole. 0 si aucune / illisible."""
    sym = str(symbol).upper()
    best = 0
    try:
        for a in fetch_announcements():
            if sym in symbols_in(a.get("title", "")):
                best = max(best, score_announcement(a))
    except Exception:
        return 0
    return best


def symbol_blocked(symbol, threshold=None):
    """VÉTO : True si une annonce à fort impact (delisting/suspension) vise ce symbole.
    Gated ANNOUNCE_VETO_ENABLED (défaut ON). FAIL-OPEN : aucune annonce lisible -> False."""
    if not int(_cfg("ANNOUNCE_VETO_ENABLED", 1)):
        return False
    thr = float(threshold if threshold is not None else _cfg("ANNOUNCE_VETO_THRESHOLD", 70))
    try:
        return symbol_risk(symbol) >= thr
    except Exception:
        return False
