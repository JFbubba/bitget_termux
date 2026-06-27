"""
econ_calendar.py — calendrier économique (LECTURE SEULE).

Classement : SAFE (donnée publique, aucun ordre, aucun secret). Source keyless :
le flux hebdomadaire Forex Factory (faireconomy.media). Sert à repérer les
FENÊTRES DE VOLATILITÉ macro (FOMC, CPI, NFP…) — utile pour ne PAS se positionner
juste avant un événement à fort impact.

parse_calendar() est PUR et testable (on injecte `now`). fetch_calendar() ajoute
le réseau et dégrade proprement.

CLI : python econ_calendar.py [DEVISE ...]   (ex. USD EUR ; défaut : toutes, impact élevé)
"""

import sys
from datetime import datetime, timezone

import requests

UA = {"User-Agent": "Mozilla/5.0"}
FEED = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
IMPACT_RANK = {"high": 3, "medium": 2, "low": 1, "holiday": 0, "non-economic": 0}


def _rank(s):
    return IMPACT_RANK.get(str(s or "").strip().lower(), 0)


def _parse_dt(s):
    if not s:
        return None
    try:
        dt = datetime.fromisoformat(str(s).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def parse_calendar(data, impact_min="High", currencies=None, within_hours=None, now=None):
    """Filtre/normalise les événements. Fonction pure (now injectable)."""
    now = now or datetime.now(timezone.utc)
    minr = _rank(impact_min)
    cset = {c.upper() for c in currencies} if currencies else None
    out = []
    for e in data or []:
        cur = (e.get("country") or e.get("currency") or "").upper()
        if cset and cur not in cset:
            continue
        if _rank(e.get("impact")) < minr:
            continue
        dt = _parse_dt(e.get("date") or e.get("time"))
        hu = round((dt - now).total_seconds() / 3600, 1) if dt else None
        if within_hours is not None and (hu is None or hu < 0 or hu > within_hours):
            continue
        out.append({
            "title": e.get("title"), "currency": cur, "impact": e.get("impact"),
            "when": dt.isoformat() if dt else (e.get("date") or e.get("time")),
            "hours_until": hu, "forecast": e.get("forecast"), "previous": e.get("previous"),
        })
    out.sort(key=lambda x: (x["hours_until"] is None, x["hours_until"] if x["hours_until"] is not None else 0))
    return out


def next_high_impact(events):
    """Premier événement à venir (hours_until >= 0) de la liste filtrée."""
    fut = [e for e in events if e.get("hours_until") is not None and e["hours_until"] >= 0]
    return fut[0] if fut else None


def fetch_calendar(impact_min="High", currencies=None, within_hours=None):
    # best-effort : calendrier vide si le flux est injoignable (jamais d'exception)
    try:
        data = requests.get(FEED, headers=UA, timeout=12).json()
    except Exception:
        return []
    return parse_calendar(data, impact_min, currencies, within_hours)


def build_report(events, title="CALENDRIER ÉCO (semaine · impact élevé)"):
    lines = [f"=== {title} ==="]
    nxt = next_high_impact(events)
    if nxt and nxt.get("hours_until") is not None:
        lines.append(f"⏱️ Prochain : [{nxt['currency']}] {nxt['title']} dans {nxt['hours_until']:.0f}h")
        lines.append("")
    if not events:
        lines.append("Aucun événement (filtre courant).")
    for e in events[:20]:
        hu = e["hours_until"]
        when = (f"dans {hu:.0f}h" if hu >= 0 else f"il y a {abs(hu):.0f}h") if hu is not None else "—"
        f = e.get("forecast") or "—"
        p = e.get("previous") or "—"
        lines.append(f"- [{e['currency']}] {e['title']} · {when} (prév {f} / préc {p})")
    lines.append("")
    lines.append("Lecture seule. Fenêtres de volatilité macro. VERDICT: SAFE")
    return "\n".join(lines)


def main():
    curr = [a.upper() for a in sys.argv[1:]] or None
    print(build_report(fetch_calendar("High", curr)))


if __name__ == "__main__":
    main()
