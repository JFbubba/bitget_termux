"""
macro_sentinel.py — « Sentinel Macro Analyst » : nowcast de RÉGIME MACRO + flux
institutionnels, à partir de sources publiques GRATUITES et SANS CLÉ.

Classement : SAFE. Lecture seule, données publiques, aucun ordre, aucun secret.
Tout passe par `runtime_cache` (TTL + stale-while-error) et tout texte externe
est assaini par `prompt_guard` avant d'être conservé/affiché.

POURQUOI (réponse à « détecter avant que ce soit dans les prix » + « se connecter
aux institutionnels pour suivre leur actualité ») :
  Le crypto ne vit pas en vase clos : il respire la LIQUIDITÉ et le RÉGIME de
  risque mondial (taux, conditions financières, crédit). Ce module lit, dès leur
  publication publique, les indicateurs avancés de la note « Sentinel Macro
  Analyst » et en déduit, de façon DÉTERMINISTE (aucun réseau de neurones), le
  régime macro dominant — les 4 mêmes régimes que le futurtester
  (expansion / slowdown / recession / recovery).

Sources (toutes vérifiées joignables, gratuites, sans clé) :
  • FRED (St. Louis Fed) `fredgraph.csv`  — séries officielles, AUCUNE clé requise :
       NFCI (conditions financières), T10Y2Y (pente 10a-2a), VIXCLS (VIX),
       BAMLH0A0HYM2 (spread High Yield OAS), FEDFUNDS, DGS10, DGS2.
  • RSS presse Fed + BCE                    — actualité des banques centrales.

Les helpers de parsing/classification sont PURS et testables ; les fetch réseau
sont enveloppés (try/except) et ne lèvent jamais vers l'appelant.
"""

import math
import re
import time
from datetime import date, timedelta

import runtime_cache as rc

try:
    import prompt_guard as pg
except Exception:  # pragma: no cover - prompt_guard est présent dans le repo
    pg = None

_UA = {"User-Agent": "Mozilla/5.0 (compatible; sentinel-macro/1.0)"}

# Séries FRED du tableau de bord « Sentinel » (id -> libellé court).
FRED_SERIES = {
    "NFCI": "conditions financières (Chicago Fed)",   # >0 = plus serrées que la moyenne
    "T10Y2Y": "pente 10a-2a",                          # <0 = inversion (signal de récession)
    "VIXCLS": "VIX",                                   # stress implicite actions
    "BAMLH0A0HYM2": "spread High Yield OAS (%)",       # stress de crédit
    "FEDFUNDS": "Fed Funds (%)",
}

# Flux RSS d'actualité des banques centrales (titres seulement, assainis).
CB_FEEDS = {
    "Fed": "https://www.federalreserve.gov/feeds/press_all.xml",
    "ECB": "https://www.ecb.europa.eu/rss/press.html",
}


# ---------- parsing PUR (testable) ----------

def parse_fred_csv(text):
    """Parse un CSV fredgraph.csv -> liste [(date_str, float)] (ignore les '.'
    manquants et l'en-tête). Pur."""
    out = []
    for line in str(text).strip().splitlines()[1:]:
        parts = line.split(",")
        if len(parts) < 2:
            continue
        d, v = parts[0].strip(), parts[1].strip()
        if not v or v == ".":
            continue
        try:
            out.append((d, float(v)))
        except ValueError:
            continue
    return out


def series_summary(points, lookback=13):
    """Résume une série [(date, val)] : dernière valeur + variation récente. Pur.

    `lookback` = nb d'observations en arrière pour la variation (def. ~1 trimestre
    de données hebdo). Retourne {last, prev, change, n}."""
    vals = [v for _, v in points]
    if not vals:
        return {"last": None, "prev": None, "change": None, "n": 0}
    last = vals[-1]
    idx = max(0, len(vals) - 1 - lookback)
    prev = vals[idx]
    return {"last": round(last, 4), "prev": round(prev, 4),
            "change": round(last - prev, 4), "n": len(vals)}


def parse_rss_titles(xml, limit=6):
    """Extrait les <title> d'un flux RSS (hors titre de canal). Pur."""
    titles = re.findall(r"<title>(.*?)</title>", str(xml), flags=re.DOTALL | re.IGNORECASE)
    cleaned = []
    for t in titles:
        t = re.sub(r"<!\[CDATA\[(.*?)\]\]>", r"\1", t, flags=re.DOTALL)
        t = re.sub(r"<[^>]+>", "", t)
        t = re.sub(r"\s+", " ", t).strip()
        if t:
            cleaned.append(t)
    # le 1er <title> est généralement le nom du canal -> on le saute
    return cleaned[1:limit + 1] if len(cleaned) > 1 else cleaned[:limit]


# ---------- nowcast de régime DÉTERMINISTE (cœur « Sentinel ») ----------

def _clamp(x, lo=-1.0, hi=1.0):
    return max(lo, min(hi, x))


def regime_nowcast(ind):
    """Classe le RÉGIME MACRO dominant à partir d'indicateurs avancés. PUR.

    `ind` = dict de niveaux/variations (clés optionnelles, robuste aux manques) :
        nfci, nfci_chg, curve, curve_chg, vix, hy, hy_chg.
    Logique (déterministe, aucun NN), fidèle à la note « Sentinel Macro Analyst » :
      • conditions financières (NFCI), pente (T10Y2Y), stress (VIX), crédit (HY OAS) ;
      • on note les 4 régimes et on prend l'argmax, avec les facteurs explicatifs.
    Retourne {regime, scores, confidence, drivers, stress, easing}."""
    g = lambda k, d=0.0: float(ind.get(k)) if ind.get(k) is not None else d

    nfci, nfci_chg = g("nfci"), g("nfci_chg")
    curve, curve_chg = g("curve", 1.0), g("curve_chg")
    vix = g("vix", 18.0)
    hy, hy_chg = g("hy", 3.5), g("hy_chg")

    # sous-signaux normalisés ~[-1,1]
    s_fin = _clamp(nfci / 0.6)                 # >0 = conditions serrées (restrictif)
    s_curve = _clamp(curve / 1.0)              # >0 = pentue (sain) ; <0 = inversée
    s_vix = _clamp((vix - 18.0) / 17.0)        # >0 = stress (18->35 sature)
    s_hy = _clamp((hy - 3.5) / 4.5)            # >0 = stress de crédit (3.5->8% sature)
    s_tighten = _clamp(nfci_chg / 0.3 + hy_chg / 1.5)   # conditions qui se durcissent
    s_ease = -s_tighten + _clamp(curve_chg / 0.4)       # re-pentification / détente

    stress = _clamp((s_vix + s_hy + max(0.0, s_fin)) / 3.0, 0.0, 1.0)
    easing = _clamp(s_ease, -1.0, 1.0)

    scores = {
        # détente, calme, pente positive, conditions lâches
        "expansion": (-s_fin) + (s_curve) + (-s_vix) + (-s_hy) + (-max(0.0, s_tighten)),
        # durcissement, pente qui s'aplatit, stress qui monte, pas encore la crise
        "slowdown": (max(0.0, s_tighten) * 1.5) + (-s_curve * 0.5) + (s_vix * 0.5)
                    + (max(0.0, s_fin) * 0.5),
        # stress élevé / crédit en détresse / inversion profonde persistante
        "recession": (s_hy * 1.5) + (s_vix) + (max(0.0, -s_curve) * 1.2)
                     + (max(0.0, s_fin)),
        # stress qui reflue depuis un pic, conditions qui se détendent, pente qui repentifie
        "recovery": (max(0.0, easing) * 1.5) + (max(0.0, curve_chg) / 0.4)
                    + (-max(0.0, s_hy - 0.3)),
    }
    regime = max(scores, key=scores.get)
    ordered = sorted(scores.values(), reverse=True)
    margin = (ordered[0] - ordered[1]) if len(ordered) > 1 else 0.0
    confidence = round(_clamp(margin / 2.0, 0.0, 1.0), 3)

    drivers = []
    if curve < 0:
        drivers.append(f"courbe 10a-2a inversée ({curve:+.2f})")
    elif curve_chg > 0.1:
        drivers.append(f"courbe se repentifie ({curve_chg:+.2f})")
    if nfci > 0:
        drivers.append(f"conditions financières serrées (NFCI {nfci:+.2f})")
    elif nfci < -0.2:
        drivers.append(f"conditions financières lâches (NFCI {nfci:+.2f})")
    if hy > 5:
        drivers.append(f"spread HY élevé ({hy:.1f}%)")
    if vix > 25:
        drivers.append(f"VIX élevé ({vix:.0f})")
    if s_tighten > 0.3:
        drivers.append("durcissement en cours")

    return {
        "regime": regime,
        "scores": {k: round(v, 3) for k, v in scores.items()},
        "confidence": confidence,
        "stress": round(stress, 3),
        "easing": round(easing, 3),
        "drivers": drivers or ["signaux mixtes / neutres"],
    }


# index du régime dans futuretester.REGIME_NAMES (expansion, slowdown, recession, recovery)
_REGIME_INDEX = {"expansion": 0, "slowdown": 1, "recession": 2, "recovery": 3}


def regime_index(regime):
    """Index du régime pour futuretester.macro_markov_path(start=...). Pur."""
    return _REGIME_INDEX.get(regime, 0)


# ---------- fetch réseau (enveloppé, jamais levé) ----------

def _http_get(url, timeout=6, retries=1, deadline=None):
    """GET texte, best-effort. `deadline` (référence time.monotonic) borne le temps
    TOTAL : on n'entame pas de nouvelle tentative au-delà -> jamais de hang en série
    sur cache froid. Lève la dernière exception (l'appelant via runtime_cache dégrade
    alors vers la dernière valeur connue / fallback)."""
    last = None
    for _ in range(retries + 1):
        if deadline is not None and time.monotonic() >= deadline:
            break
        try:
            # requests et non urllib (audit 03/07) : FRED time-out systématiquement les
            # requêtes urllib (empreinte TLS/headers) alors que requests passe en ~0.4 s
            # depuis le même hôte — le sentinel était AVEUGLE (nowcast n/a, 18 s brûlées
            # à chaque cache froid), seul module du dépôt encore sur urllib.
            import requests
            r = requests.get(url, headers=_UA, timeout=timeout)
            r.raise_for_status()
            return r.text
        except Exception as e:  # 503 throttling FRED, lenteur RSS, etc. -> on retente
            last = e
    raise last if last else TimeoutError("http_get: budget réseau dépassé")


def fred_series(series_id, days=420, ttl=21600, deadline=None):
    """Série FRED [(date, val)] via fredgraph.csv (SANS CLÉ), cachée 6 h par défaut.
    Best-effort : ne lève jamais (liste vide si indisponible). `deadline` borne le réseau."""
    def fetch():
        cosd = (date.today() - timedelta(days=days)).isoformat()
        url = (f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}"
               f"&cosd={cosd}")
        return parse_fred_csv(_http_get(url, deadline=deadline))
    return rc.get(f"fred:{series_id}", ttl, fetch, fallback=[])


def dashboard(ttl=21600, budget=18.0):
    """Tableau de bord macro « Sentinel » : pour chaque série FRED, dernière valeur
    + variation récente. Best-effort, cache 6 h. `budget` borne le temps réseau TOTAL
    (anti-hang sur cache froid) : au-delà, les séries restantes dégradent en fallback.
    Retourne dict series_id -> résumé."""
    deadline = time.monotonic() + budget
    out = {}
    for sid, label in FRED_SERIES.items():
        pts = fred_series(sid, ttl=ttl, deadline=deadline)
        s = series_summary(pts)
        s["label"] = label
        out[sid] = s
    return out


def _dashboard_to_indicators(dash):
    """Mappe le dashboard FRED -> dict d'indicateurs pour regime_nowcast. Pur."""
    def lv(sid, k="last"):
        return (dash.get(sid) or {}).get(k)
    return {
        "nfci": lv("NFCI"), "nfci_chg": lv("NFCI", "change"),
        "curve": lv("T10Y2Y"), "curve_chg": lv("T10Y2Y", "change"),
        "vix": lv("VIXCLS"),
        "hy": lv("BAMLH0A0HYM2"), "hy_chg": lv("BAMLH0A0HYM2", "change"),
    }


def nowcast(ttl=21600):
    """Nowcast de régime LIVE : lit le dashboard FRED et classe le régime. Best-effort."""
    dash = dashboard(ttl=ttl)
    ind = _dashboard_to_indicators(dash)
    if all(v is None for v in ind.values()):
        return {"regime": "n/a", "confidence": 0.0, "drivers": ["données macro indisponibles"],
                "indicators": ind, "dashboard": dash}
    out = regime_nowcast(ind)
    out["indicators"] = ind
    out["dashboard"] = dash
    return out


def central_bank_headlines(limit=4, ttl=3600, budget=8.0):
    """Titres d'actualité des banques centrales (Fed, BCE), ASSAINIS. Best-effort.
    `budget` borne le temps réseau TOTAL (anti-hang sur cache froid).

    Réponse à « se connecter aux institutionnels pour suivre leur actualité » :
    on lit les flux RSS officiels et on n'en garde que les TITRES, passés par
    prompt_guard (le contenu externe n'est jamais traité comme une instruction)."""
    def fetch():
        deadline = time.monotonic() + budget
        items = []
        for name, url in CB_FEEDS.items():
            try:
                titles = parse_rss_titles(_http_get(url, deadline=deadline), limit=limit)
            except Exception:
                titles = []
            for t in titles:
                if pg is not None:
                    t = pg.sanitize(t, max_len=300)
                items.append({"source": name, "title": t})
        return items
    return rc.get("cb_headlines", ttl, fetch, fallback=[])


def snapshot(ttl=21600):
    """Vue macro complète (nowcast régime + indicateurs + actualité BC). Best-effort."""
    nc = nowcast(ttl=ttl)
    return {
        "regime": nc.get("regime"),
        "confidence": nc.get("confidence"),
        "stress": nc.get("stress"),
        "drivers": nc.get("drivers"),
        "indicators": nc.get("indicators"),
        "dashboard": nc.get("dashboard"),
        "headlines": central_bank_headlines(),
    }


def build_report(snap):
    """Rapport texte lisible du snapshot macro. Pur."""
    lines = ["=== SENTINEL MACRO ANALYST ===",
             f"Régime dominant : {snap.get('regime', 'n/a')}  "
             f"(confiance {snap.get('confidence', 0)}, stress {snap.get('stress', 'n/a')})"]
    for d in (snap.get("drivers") or []):
        lines.append(f"  • {d}")
    dash = snap.get("dashboard") or {}
    if dash:
        lines.append("")
        lines.append("Indicateurs (dernier · Δ récent) :")
        for sid, s in dash.items():
            if s.get("last") is not None:
                lines.append(f"  - {sid:<13} {s['last']:>8} · {s.get('change', 0):+} "
                             f"| {s.get('label', '')}")
    hl = snap.get("headlines") or []
    if hl:
        lines.append("")
        lines.append("Actualité banques centrales :")
        for h in hl[:6]:
            lines.append(f"  [{h['source']}] {h['title']}")
    lines.append("")
    lines.append("Nowcast macro déterministe, LECTURE SEULE. Aucun ordre. VERDICT: SAFE")
    return "\n".join(lines)


def main():
    print(build_report(snapshot()))


if __name__ == "__main__":
    main()
