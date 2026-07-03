"""
kalshi_probe.py — marchés de PRÉDICTION macro (Kalshi, lecture seule). SAFE.

§58 : la clé KALSHI_API_KEY dormait dans le .env — testée fonctionnelle. Les
séries KXFED / KXCPI / KXFEDDECISION portent les échéances macro qui font
bouger la crypto (décisions Fed, prints CPI) avec leurs probabilités implicites
de marché. Usage ADVISORY : proximité de la PROCHAINE échéance = risque
d'événement (le mandat a déjà un black-out macro ; ceci lui donne une source
vivante), affichée dans le snapshot macro. AUCUN ordre, AUCUN vote.

Fonctions de parsing PURES et testables ; réseau enveloppé, caché, ne lève jamais.
CLI : python kalshi_probe.py
"""

import os
import time
from datetime import datetime, timezone

BASE = "https://api.elections.kalshi.com/trade-api/v2"
SERIES = ("KXFEDDECISION", "KXCPI")


def _cle():
    key = os.getenv("KALSHI_API_KEY")
    if key:
        return key
    try:
        from dotenv import load_dotenv
        load_dotenv()
        return os.getenv("KALSHI_API_KEY")
    except Exception:
        return None


def _iso_vers_ts(s):
    """'2028-01-26T19:00:00Z' -> epoch s. PUR. None si illisible."""
    try:
        return datetime.fromisoformat(str(s).replace("Z", "+00:00")).timestamp()
    except (ValueError, TypeError):
        return None


def parser_evenements(payload, now=None):
    """Événements Kalshi -> [{serie, titre, echeance_ts, jours}] TRIÉS par
    échéance croissante, échéances PASSÉES exclues. PUR. [] si illisible."""
    now = time.time() if now is None else now
    out = []
    for e in (payload or {}).get("events") or []:
        if not isinstance(e, dict):
            continue
        ts = _iso_vers_ts(e.get("strike_date"))
        if ts is None:
            for m in e.get("markets") or []:
                ts = _iso_vers_ts((m or {}).get("close_time"))
                if ts:
                    break
        if ts is None or ts <= now:
            continue
        out.append({"serie": e.get("series_ticker"), "titre": e.get("title"),
                    "echeance_ts": int(ts), "jours": round((ts - now) / 86400.0, 1)})
    out.sort(key=lambda x: x["echeance_ts"])
    return out


def evenement_imminent(evenements, now=None, pre_min=30.0, post_min=15.0):
    """L'événement macro dont la fenêtre de BLACK-OUT est active (mandat :
    dégager le risque pre_min avant -> post_min après l'annonce), ou None. PUR.
    Fail-open : liste vide/illisible -> None (l'absence de calendrier ne bloque
    jamais le trading — on bride sur donnée, pas sur panne)."""
    now = time.time() if now is None else now
    for e in evenements or []:
        ts = (e or {}).get("echeance_ts")
        if ts is None:
            continue
        if ts - pre_min * 60.0 <= now <= ts + post_min * 60.0:
            return e
    return None


def prochaine_echeance(evenements):
    """Le prochain événement macro (ou None). PUR."""
    return evenements[0] if evenements else None


def fetch_evenements(ttl=3600):
    """Événements macro ouverts des séries suivies (cachés 1 h, best-effort []).
    Une requête par série et par heure — poli avec l'API."""
    def fetch():
        import requests
        cle = _cle()
        if not cle:
            return []
        evs = []
        for st in SERIES:
            # limit large : l'API liste par date de CRÉATION (les échéances 2027-28
            # d'abord) — sans ça, les événements PROCHES passent sous le limit.
            r = requests.get(f"{BASE}/events",
                             params={"series_ticker": st, "limit": 100, "status": "open"},
                             headers={"Authorization": f"Bearer {cle}"}, timeout=10)
            r.raise_for_status()
            evs += parser_evenements(r.json())
        evs.sort(key=lambda x: x["echeance_ts"])
        return evs
    try:
        import runtime_cache as rc
        return rc.get("kalshi_events", ttl, fetch, fallback=[])
    except Exception:
        return []


def snapshot():
    """{prochain: {...}|None, n_suivis} pour le snapshot macro. Best-effort."""
    evs = fetch_evenements()
    return {"prochain": prochaine_echeance(evs), "n_suivis": len(evs)}


def build_report(s=None):
    s = snapshot() if s is None else s
    p = s.get("prochain")
    lignes = ["=== KALSHI — échéances macro (marchés de prédiction, lecture seule) ==="]
    if p:
        lignes.append(f"Prochaine échéance : {p['titre']} ({p['serie']}) dans {p['jours']} j")
    else:
        lignes.append("Aucune échéance lisible (clé absente ou API muette) — advisory, sans impact.")
    lignes.append(f"Événements suivis : {s.get('n_suivis', 0)} (séries {', '.join(SERIES)})")
    lignes.append("Lecture seule. Aucun ordre, aucun vote. VERDICT: SAFE")
    return "\n".join(lignes)


def main():
    print(build_report())


if __name__ == "__main__":
    main()
