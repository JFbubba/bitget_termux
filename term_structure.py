"""term_structure.py — courbe des ÉCHÉANCES BTC/ETH (Deribit) et basis annualisé. LECTURE SEULE.

Classement : SAFE. Réseau public sans clé, aucun ordre, aucun secret.

POURQUOI (extraction du 20/07/2026) : `carry_monitor.py` ne mesure que la base **perp ↔ spot**
sur Bitget. La **courbe des échéances datées** est une autre information, que le bot ne voyait pas
du tout : sa PENTE est un descripteur de régime de carry, et son passage en **backwardation** est
un marqueur de stress (les détenteurs paient pour sortir plutôt que pour porter).

CLASSEMENT D'INTENTION (ERR-016) — à lire avant d'en faire quoi que ce soit : ceci est un
**DESCRIPTEUR DE RÉGIME / CARRY**, PAS un prédicteur directionnel. Il se juge sur le régime qu'il
identifie et sur le sizing de carry qu'il pourrait moduler — **jamais à l'IC directionnelle**.
Mesurer son « edge » au sens d'un signal serait poser la mauvaise question (cf. ERR-017).

MÉTHODE : le **PERPÉTUEL sert d'ancre spot** (il n'a pas d'échéance, il colle au spot par le
funding), puis chaque échéance datée reçoit son basis annualisé
    basis_pct = (prix_fut / ancre − 1) × (365 / jours) × 100
signe positif = contango (porter rapporte), négatif = backwardation (stress).

⚠️ GARDE DES 7 JOURS — leçon EMPRUNTÉE, déjà payée en production par la source de l'idée : sous
environ une semaine, le multiplicateur 365/jours transforme le bruit de funding en « basis » à
±30 % (cas constaté : une décote de 112 $ à 3 jours s'annualisait en −24 %). Toute échéance sous
`MIN_JOURS_BASIS` est ÉCARTÉE, et le nombre d'écartés est rapporté — jamais de filtrage silencieux.

Contrat d'échec : chaque fetch dégrade vers son neutre ([] / None), les cœurs purs tolèrent None
et champs manquants. Ne lève jamais.

CLI : python term_structure.py [BTC|ETH]
"""

import re
import time
import datetime

import requests

from config_utils import cfg as _cfg
from numeric_utils import safe_float

BOOK_URL = "https://www.deribit.com/api/v2/public/get_book_summary_by_currency"
UA = {"User-Agent": "Mozilla/5.0"}

# Seuil de la garde ci-dessus. Ne pas descendre sous 7 sans re-mesurer le bruit court-terme.
MIN_JOURS_BASIS = 7.0
# Deribit règle ses échéances à 08:00 UTC.
HEURE_ECHEANCE_UTC = 8
# Bande morte du régime : sous ce basis médian (en %), la courbe est dite PLATE.
SEUIL_PLAT_PCT = 0.5

_MOIS = {m: i + 1 for i, m in enumerate(
    ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"])}
_RE_ECHEANCE = re.compile(r"^[A-Z]+-(\d{1,2})([A-Z]{3})(\d{2})$")


def jours_echeance(instrument, now=None):
    """PURE. Jours (float) jusqu'à l'échéance d'un instrument daté Deribit, réglée à 08:00 UTC.
    None pour le PERPÉTUEL (c'est l'ancre, pas une échéance) et pour tout nom illisible."""
    if not isinstance(instrument, str):
        return None
    m = _RE_ECHEANCE.match(instrument.strip().upper())
    if not m:
        return None
    jour, mois, an = int(m.group(1)), _MOIS.get(m.group(2)), 2000 + int(m.group(3))
    if not mois:
        return None
    try:
        exp = datetime.datetime(an, mois, jour, HEURE_ECHEANCE_UTC, tzinfo=datetime.UTC).timestamp()
    except ValueError:                       # ex. 32 d'un mois : date impossible
        return None
    now = time.time() if now is None else float(now)
    return (exp - now) / 86400.0


def basis_annualise_pct(prix_fut, ancre, jours):
    """PURE. Basis annualisé en %, ou None si non calculable / sous la garde des 7 jours.
    C'est ici que vit la leçon empruntée : on refuse de produire un chiffre plutôt que d'en
    produire un faux."""
    f, a, j = safe_float(prix_fut), safe_float(ancre), safe_float(jours)
    if f is None or a is None or j is None or a <= 0 or f <= 0:
        return None
    if j < MIN_JOURS_BASIS:
        return None
    return (f / a - 1.0) * (365.0 / j) * 100.0


def _prix(row):
    """Prix de référence d'une ligne : mark, à défaut mid, à défaut last."""
    for k in ("mark_price", "mid_price", "last"):
        v = safe_float((row or {}).get(k))
        if v is not None and v > 0:
            return v
    return None


def courbe(rows, now=None):
    """PURE. Construit la courbe : ancre = PERPÉTUEL, puis un point par échéance retenue.
    Sans perpétuel dans le lot -> AUCUNE ancre et AUCUN point (on n'invente jamais l'ancre).
    Retourne {ancre_usd, points:[{instrument, jours, prix, basis_pct}], n_ecartes_sous_seuil}."""
    ancre, dates, ecartes = None, [], 0
    for r in rows or []:
        if not isinstance(r, dict):
            continue
        nom = r.get("instrument_name")
        if not isinstance(nom, str):
            continue
        px = _prix(r)
        if px is None:
            continue
        if nom.strip().upper().endswith("-PERPETUAL"):
            ancre = px
            continue
        j = jours_echeance(nom, now=now)
        if j is None or j <= 0:
            continue
        dates.append((nom, j, px))
    points = []
    if ancre is not None:
        for nom, j, px in dates:
            b = basis_annualise_pct(px, ancre, j)
            if b is None:                                # écarté par la garde des 7 jours
                ecartes += 1
                continue
            points.append({"instrument": nom, "jours": round(j, 4),
                           "prix": px, "basis_pct": round(b, 4)})
        points.sort(key=lambda p: p["jours"])
    return {"ancre_usd": ancre, "points": points, "n_ecartes_sous_seuil": ecartes}


def _mediane(xs):
    ys = sorted(xs)
    n = len(ys)
    if not n:
        return None
    return ys[n // 2] if n % 2 else (ys[n // 2 - 1] + ys[n // 2]) / 2.0


def regime(c):
    """PURE. Régime de la courbe : contango / plat / backwardation (= stress), plus la pente
    entre la première et la dernière échéance retenue. `regime` None si rien n'est mesurable —
    absence de mesure n'est PAS un stress."""
    pts = (c or {}).get("points") or []
    if not pts:
        return {"regime": None, "pente_pct": None, "basis_median_pct": None, "stress": False}
    bs = [p["basis_pct"] for p in pts]
    med = _mediane(bs)
    pente = (pts[-1]["basis_pct"] - pts[0]["basis_pct"]) if len(pts) > 1 else 0.0
    if med is None:
        etat = None
    elif med < -SEUIL_PLAT_PCT:
        etat = "backwardation"
    elif med > SEUIL_PLAT_PCT:
        etat = "contango"
    else:
        etat = "plat"
    return {"regime": etat, "pente_pct": round(pente, 4),
            "basis_median_pct": round(med, 4) if med is not None else None,
            "stress": etat == "backwardation"}


def fetch_book(devise="BTC"):
    """Résumé de carnet des futures d'une devise (public, sans clé), caché. [] si injoignable."""
    def _fetch():
        rep = requests.get(BOOK_URL, params={"currency": str(devise).upper(), "kind": "future"},
                           headers=UA, timeout=8)
        rep.raise_for_status()
        res = (rep.json() or {}).get("result")
        return res if isinstance(res, list) else []

    try:
        import runtime_cache as rc
        return rc.get(f"deribit_term:{devise}", _cfg("DERIBIT_TERM_TTL_S", 900),
                      _fetch, fallback=[])
    except Exception:
        return []


def snapshot(devise="BTC", rows=None, now=None):
    """Instantané : courbe + régime. Ne lève jamais."""
    rows = fetch_book(devise) if rows is None else rows
    c = courbe(rows, now=now)
    return {"devise": str(devise).upper(), **c, **regime(c)}


def _n(v, motif="{:+.2f}"):
    return motif.format(v) if isinstance(v, (int, float)) else "—"


def build_report(snaps=None, devises=("BTC", "ETH")):
    """Rapport texte, lecture seule."""
    snaps = [snapshot(d) for d in devises] if snaps is None else snaps
    lignes = ["=== STRUCTURE PAR TERME (Deribit, public sans clé) — DESCRIPTEUR DE RÉGIME ===",
              "  (le perpétuel sert d'ancre spot · basis annualisé · échéances < "
              f"{MIN_JOURS_BASIS:.0f} j ÉCARTÉES : bruit de funding annualisé)"]
    for s in snaps or []:
        if not s.get("points"):
            lignes.append(f"  {s.get('devise', '?')} : courbe indisponible "
                          f"({s.get('n_ecartes_sous_seuil', 0)} échéance(s) écartée(s) sous seuil)")
            continue
        etat = s.get("regime") or "?"
        marque = " 🛑 STRESS" if s.get("stress") else ""
        lignes.append(f"  {s['devise']} — {etat.upper()}{marque} · ancre {s['ancre_usd']:.2f} $ · "
                      f"basis médian {_n(s.get('basis_median_pct'))} % · "
                      f"pente {_n(s.get('pente_pct'))} pt"
                      + (f" · {s['n_ecartes_sous_seuil']} écartée(s)"
                         if s.get("n_ecartes_sous_seuil") else ""))
        for p in s["points"]:
            lignes.append(f"      {p['instrument']:16s} {p['jours']:7.1f} j · {p['prix']:11.2f} $ "
                          f"· basis {_n(p['basis_pct'])} %")
    lignes.append("Descripteur de RÉGIME/CARRY — jamais un signal directionnel (ERR-016). "
                  "Lecture seule. VERDICT: SAFE")
    return "\n".join(lignes)


def main():
    import sys
    devises = tuple(a.upper() for a in sys.argv[1:] if not a.startswith("-")) or ("BTC", "ETH")
    print(build_report(devises=devises))


if __name__ == "__main__":
    main()
