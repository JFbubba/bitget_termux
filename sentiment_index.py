"""
sentiment_index.py — Fear & Greed Index crypto (LECTURE SEULE).

Classement : SAFE (donnee publique, aucune cle, aucun ordre, aucun secret).
Source : alternative.me (gratuit, sans cle).

CLI : python sentiment_index.py
"""

import requests

FNG_URL = "https://api.alternative.me/fng/"


def parse_fear_greed(data):
    """data {"data":[{"value","value_classification","timestamp"}]} -> dict."""
    items = data.get("data") or []
    if not items:
        return None
    first = items[0]
    try:
        value = int(first.get("value"))
    except (TypeError, ValueError):
        value = None
    return {
        "value": value,
        "classification": first.get("value_classification"),
        "timestamp": first.get("timestamp"),
    }


def fetch_fear_greed(limit=1):
    # best-effort : None si la source est injoignable (jamais d'exception).
    # Tous les appelants gèrent déjà None (poids sentiment neutre).
    try:
        response = requests.get(FNG_URL, params={"limit": str(limit)}, timeout=10)
        response.raise_for_status()
        return parse_fear_greed(response.json())
    except Exception:
        return None


# ---------- historique PROFOND (§75 : rejeu du vote sentiment sur des années) ----------
from pathlib import Path as _Path

_HIST_FILE = _Path(__file__).resolve().parent / "data_history" / "FEAR_GREED.json"


def load_history():
    """[(ts_ms, valeur 0-100), ...] triés croissant (un point par JOUR). [] si rien."""
    try:
        import json
        rows = json.loads(_HIST_FILE.read_text(encoding="utf-8"))
        return sorted(rows, key=lambda r: r[0]) if isinstance(rows, list) else []
    except Exception:
        return []


def download_history(timeout=25):
    """Télécharge l'historique COMPLET du Fear & Greed (limit=0 : depuis 2018) et le
    consolide sur disque (dédup par jour, écriture atomique, gitignored comme le
    funding). Même style que funding_history.download. Retourne le nombre de points."""
    import json
    resp = requests.get(FNG_URL, params={"limit": "0", "format": "json"}, timeout=timeout)
    resp.raise_for_status()
    connu = {r[0]: r for r in load_history()}
    for it in (resp.json().get("data") or []):
        try:
            connu[int(it["timestamp"]) * 1000] = [int(it["timestamp"]) * 1000, int(it["value"])]
        except (KeyError, TypeError, ValueError):
            continue
    rows = sorted(connu.values(), key=lambda r: r[0])
    _HIST_FILE.parent.mkdir(exist_ok=True)
    tmp = _HIST_FILE.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(rows), encoding="utf-8")
    import os
    os.replace(tmp, _HIST_FILE)
    return len(rows)


def build_report(fng):
    if not fng:
        return "=== FEAR & GREED ===\nIndisponible.\nVERDICT: SAFE"
    return "\n".join([
        "=== FEAR & GREED (crypto) ===",
        f"Indice  : {fng['value']} / 100",
        f"Etat    : {fng['classification']}",
        "",
        "Lecture seule. Aucun ordre. VERDICT: SAFE",
    ])


def main():
    print(build_report(fetch_fear_greed()))


if __name__ == "__main__":
    main()
